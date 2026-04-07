import asyncio
import logging
import sys
import os
import random
import socket
import traceback
from logging.handlers import RotatingFileHandler
from datetime import datetime
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from typing import Dict

from sqlalchemy.orm import Session
from sqlalchemy import func
from rich.console import Console

from app.agents.sender import send_email_via_smtp
from app.backup_manager import backup_manager

# --- KONFIGURACJA LOGOWANIA (ENTERPRISE) ---
LOG_FILE = "engine.log"

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
console_handler.setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger("nexus_engine")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("apify_client").setLevel(logging.WARNING)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
console = Console()

# Importy z aplikacji
from app.database import engine, Client, Lead, Campaign
from app.agents.scout import run_scout_async
from app.agents.strategy import generate_strategy
from app.agents.researcher import analyze_lead_async
from app.agents.writer import generate_email
from app.scheduler import process_followups, save_draft_via_imap
from app.agents.inbox import check_inbox
from app.warmup import calculate_daily_limit
from app.rodo_manager import is_opted_out
from app import stats_manager
from app.brief_sync import sync_briefs_to_clients

# --- KONFIGURACJA SKALOWANIA ---
MAX_CONCURRENT_AGENTS = 20
DISPATCHER_INTERVAL = 5

# --- OKIENKO WYSYŁKOWE (godziny lokalne) ---
SENDING_WINDOW_START = 8   # 08:00
SENDING_WINDOW_END = 20    # 20:00


def _is_sending_window() -> bool:
    """Czy jesteśmy w okienku wysyłkowym (8:00-20:00)?"""
    return SENDING_WINDOW_START <= datetime.now().hour < SENDING_WINDOW_END

# ==========================================
# PHASE 2: Optional imports
# ==========================================
PHASE2_ENABLED = False
cache_manager = None
rate_limiter = None
queue_manager = None
QueueType = None

try:
    from app.cache_manager import cache_manager
    from app.rate_limiter import rate_limiter
    from app.queue_manager import queue_manager, QueueType
    PHASE2_ENABLED = True
    logger.info("✅ Phase 2 modules loaded (Redis cache, queues, rate limiting)")
except ImportError as e:
    logger.warning(f"⚠️ Phase 2 modules not found - running in legacy mode: {e}")

# ==========================================
# CONFIGURATION
# ==========================================
BACKUP_INTERVAL_SECONDS = 6 * 3600
BRIEF_SYNC_INTERVAL = 30 * 60  # Sprawdzaj zmiany w briefach co 30 minut
USE_QUEUES = os.getenv("USE_QUEUES", "false").lower() == "true"
STATS_INTERVAL = 300


# ---------------------------------------------------------------------------
# HELPERY POMOCNICZE
# ---------------------------------------------------------------------------

def _log_sync_result(sync_result: dict) -> None:
    """Loguje wynik synchronizacji briefów w czytelny sposób."""
    if not sync_result:
        return
    created = sync_result.get("created", 0)
    updated = sync_result.get("updated", 0)
    deactivated = sync_result.get("deactivated", 0)

    if created or updated or deactivated:
        parts = []
        if created:
            parts.append(f"{created} nowych")
        if updated:
            parts.append(f"{updated} zaktualizowanych")
        if deactivated:
            parts.append(f"{deactivated} dezaktywowanych")
        console.print(f"[bold green]🔄 Brief Sync:[/bold green] {', '.join(parts)}")
    else:
        logger.debug("[SYNC] Brak zmian w briefach.")


def get_today_progress(session: Session, client: Client) -> int:
    """Zwraca liczbę PIERWSZYCH maili wysłanych dzisiaj (follow-upy się nie liczą)."""
    today = datetime.now().date()
    return session.query(Lead).join(Campaign).filter(
        Campaign.client_id == client.id,
        Lead.status == "SENT",
        Lead.step_number == 1,
        func.date(Lead.sent_at) == today,
    ).count()


def _get_pipeline_counts(session: Session, client: Client) -> dict:
    """Ile leadów jest na poszczególnych etapach pipeline'u (step_number=1, nowe firmy)."""
    base = session.query(Lead).join(Campaign).filter(
        Campaign.client_id == client.id,
        Lead.step_number == 1,
    )
    return {
        "new": base.filter(Lead.status == "NEW").count(),
        "analyzed": base.filter(Lead.status == "ANALYZED").count(),
        "drafted": base.filter(Lead.status == "DRAFTED").count(),
    }


# ---------------------------------------------------------------------------
# ATOMOWE FAZY CYKLU
# ---------------------------------------------------------------------------

async def _handle_hygiene(session: Session, client: Client, use_queues: bool) -> None:
    """FAZA 0: Sprawdza skrzynkę i przetwarza follow-upy."""
    await asyncio.to_thread(check_inbox, session, client)
    await asyncio.to_thread(process_followups, session, client, use_queue=use_queues)


async def _send_email(
    session: Session,
    client: Client,
    draft: Lead,
    worker_id: str,
    use_queues: bool,
) -> bool:
    """Wysyła email przez SMTP (tryb AUTO)."""
    if PHASE2_ENABLED:
        can_send, reason = rate_limiter.check_email_limit(client)
        if not can_send:
            console.print(f"[yellow]⏸️  {client.name}:[/yellow] {reason}")
            logger.warning(f"[{client.name}] Rate limited: {reason}")
            if use_queues:
                queue_manager.push_lead(draft.id, QueueType.DRAFTED)
            return False

    console.print(f"[bold green]🚀 {client.name}:[/bold green] WYSYŁAM (AUTO) do {draft.company.name}...")
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "sending_email")

    await asyncio.sleep(random.randint(3, 10))
    success = await asyncio.to_thread(send_email_via_smtp, draft, client)

    if success:
        draft.status = "SENT"
        draft.sent_at = datetime.now(PL_TZ)
        session.commit()
        logger.info(f"[{client.name}] SENT email to {draft.company.name}")
        # STATS: email wysłany (z informacją o kroku followup)
        try:
            step = getattr(draft, 'step_number', 1) or 1
            stats_manager.increment_sent(session, client.id, count=1, step=step)
        except Exception:
            pass

        if PHASE2_ENABLED:
            rate_limiter.record_email_sent(client.id)
            queue_manager.unmark_processing(draft.id)
            delay = rate_limiter.calculate_next_email_delay(client.id)
            console.print(f"   ☕ {client.name}: Adaptive delay {delay}s")
            await asyncio.sleep(delay)
        else:
            wait_time = random.randint(60, 300)
            console.print(f"   ☕ {client.name}: Przerwa {wait_time}s")
            await asyncio.sleep(wait_time)
    else:
        logger.error(f"[{client.name}] SMTP Error for {draft.company.name}")
        if use_queues and PHASE2_ENABLED:
            queue_manager.push_lead(draft.id, QueueType.DRAFTED)
            queue_manager.unmark_processing(draft.id)

    return True


async def _save_draft_imap(
    session: Session,
    client: Client,
    draft: Lead,
    worker_id: str,
) -> bool:
    """Zapisuje draft przez IMAP (tryb DRAFT)."""
    console.print(f"[green]💾 {client.name}:[/green] Zapisuję draft...")
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "saving_draft")

    success, _info = await asyncio.to_thread(save_draft_via_imap, draft, client)
    if success:
        draft.status = "SENT"
        draft.sent_at = datetime.now(PL_TZ)
        session.commit()
        logger.info(f"[{client.name}] DRAFT SAVED for {draft.company.name}")
        # STATS: draft zapisany (liczymy jako sent)
        try:
            step = getattr(draft, 'step_number', 1) or 1
            stats_manager.increment_sent(session, client.id, count=1, step=step)
        except Exception:
            pass
        if PHASE2_ENABLED:
            queue_manager.unmark_processing(draft.id)

    return True


async def _handle_drafts(
    session: Session,
    client: Client,
    worker_id: str,
    use_queues: bool,
) -> bool:
    """FAZA 1: Wysyła lub zapisuje gotowe drafty (DRAFTED → SENT).

    - AUTO mode: wysyła JEDEN mail + ludzki delay (wywoływane wielokrotnie przez cykl)
    - DRAFT mode: zapisuje WSZYSTKIE do IMAP od razu (brak potrzeby imitacji)
    Bramka opt-out sprawdzana PRZED próbą wysyłki.
    """
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "checking_drafts")
        
    # DNS VALIDATOR (Wektor 4 Antyspam)
    from app.tools import verify_sender_dns
    if client.smtp_user and "@" in client.smtp_user:
        domain = client.smtp_user.split("@")[1]
        dns_status = verify_sender_dns(domain)
        if not dns_status.get("spf_ok") or not dns_status.get("dmarc_ok"):
            logger.error(f"🛑 [BLOKADA ANTYSZAM] Domena '{domain}' klienta '{client.name}' nie posiada poprawnych rekordów SPF lub DMARC. Wysyłka wstrzymana.")
            # STATS: blokada DNS
            try:
                stats_manager.increment_dns_block(session, client.id)
            except Exception:
                pass
            return False

    sending_mode = getattr(client, "sending_mode", "DRAFT")

    # --- DRAFT MODE: zrzuć WSZYSTKIE na raz do IMAP ---
    if sending_mode != "AUTO":
        drafts = session.query(Lead).join(Campaign).filter(
            Campaign.client_id == client.id,
            Lead.status == "DRAFTED",
        ).all()

        if not drafts:
            return False

        saved = 0
        for draft in drafts:
            if is_opted_out(session, draft.target_email or ""):
                draft.status = "BLACKLISTED"
                session.commit()
                continue

            success, _info = await asyncio.to_thread(save_draft_via_imap, draft, client)
            if success:
                draft.status = "SENT"
                draft.sent_at = datetime.now(PL_TZ)
                session.commit()
                saved += 1
                logger.info(f"[{client.name}] DRAFT SAVED: {draft.company.name}")
                if PHASE2_ENABLED:
                    queue_manager.unmark_processing(draft.id)

        if saved > 0:
            console.print(f"[green]💾 {client.name}:[/green] Zapisano {saved} draftów do IMAP")
        return saved > 0

    # --- AUTO MODE: wyślij JEDEN mail z ludzkim delay'em ---
    draft = None
    if use_queues and PHASE2_ENABLED:
        lead_data = queue_manager.pop_lead([QueueType.DRAFTED], worker_id)
        if lead_data:
            draft = session.query(Lead).filter(Lead.id == lead_data["lead_id"]).first()

    if not draft:
        draft = session.query(Lead).join(Campaign).filter(
            Campaign.client_id == client.id,
            Lead.status == "DRAFTED",
        ).first()

    if not draft:
        return False

    # OPT-OUT CHECK
    if is_opted_out(session, draft.target_email or ""):
        logger.warning(f"[{client.name}] BLACKLIST: {draft.target_email}")
        draft.status = "BLACKLISTED"
        session.commit()
        if use_queues and PHASE2_ENABLED:
            queue_manager.unmark_processing(draft.id)
        return True

    return await _send_email(session, client, draft, worker_id, use_queues)


async def _handle_writing(
    session: Session,
    client: Client,
    worker_id: str,
    use_queues: bool,
) -> bool:
    """FAZA 1D: Generuje maile dla leadów ze statusem ANALYZED."""
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "checking_analyzed")

    analyzed = None
    if use_queues and PHASE2_ENABLED:
        lead_data = queue_manager.pop_lead([QueueType.ANALYZED], worker_id)
        if lead_data:
            analyzed = session.query(Lead).filter(Lead.id == lead_data["lead_id"]).first()

    if not analyzed:
        analyzed = session.query(Lead).join(Campaign).filter(
            Campaign.client_id == client.id,
            Lead.status == "ANALYZED",
        ).first()

    if not analyzed:
        return False

    console.print(f"[cyan]✍️  {client.name}:[/cyan] Piszę maila do {analyzed.company.name}...")
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "writing_email")

    await asyncio.to_thread(generate_email, session, analyzed.id)

    if PHASE2_ENABLED:
        queue_manager.unmark_processing(analyzed.id)

    return True


async def _handle_research(
    session: Session,
    client: Client,
    worker_id: str,
    use_queues: bool,
) -> bool:
    """FAZA 2E: Analizuje nowe leady (NEW → ANALYZED)."""
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "checking_new")

    new_lead = None
    if use_queues and PHASE2_ENABLED:
        lead_data = queue_manager.pop_lead([QueueType.NEW], worker_id)
        if lead_data:
            new_lead = session.query(Lead).filter(Lead.id == lead_data["lead_id"]).first()

    if not new_lead:
        new_lead = session.query(Lead).join(Campaign).filter(
            Campaign.client_id == client.id,
            Lead.status == "NEW",
        ).first()

    if not new_lead:
        return False

    console.print(f"[blue]🔬 {client.name}:[/blue] Analizuję {new_lead.company.domain}...")
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "researching")

    await analyze_lead_async(session, new_lead.id)

    if PHASE2_ENABLED:
        queue_manager.unmark_processing(new_lead.id)

    return True


async def _handle_scouting(
    session: Session,
    client: Client,
    worker_id: str,
) -> bool:
    """FAZA 2F: Szuka nowych leadów przez Google Maps (20% szans per cykl)."""
    if PHASE2_ENABLED:
        queue_manager.register_worker(worker_id, client.id, "scouting")

    campaign = session.query(Campaign).filter(
        Campaign.client_id == client.id,
        Campaign.status == "ACTIVE",
    ).order_by(Campaign.id.desc()).first()

    if not campaign or random.random() >= 0.2:
        return False

    console.print(f"[bold red]🕵️ {client.name}:[/bold red] Sprawdzam strategię...")
    strategy = await asyncio.to_thread(
        generate_strategy, client, campaign.strategy_prompt, campaign.id
    )

    if strategy and getattr(strategy, "search_queries", None):
        strategy.search_queries = strategy.search_queries[:2]
        await run_scout_async(session, campaign.id, strategy)
        return True

    return False


# ---------------------------------------------------------------------------
# GŁÓWNY WORKER (ORKIESTRATOR)
# ---------------------------------------------------------------------------

async def run_client_cycle(
    client_id: int,
    semaphore: asyncio.Semaphore,
    worker_id: str = None,
    use_queues: bool = False,
) -> bool:
    """
    JEDEN OBRÓT KOŁA ZAMACHOWEGO (Worker) — NEXUS v3.1

    Logika dzienna:
    ┌─────────────────────────────────────────────────────────┐
    │  OKIENKO WYSYŁKOWE (8:00-20:00):                       │
    │    1. Higiena (inbox + follow-upy)                      │
    │    2. Wyślij DRAFTED (AUTO z ludzkim delay / DRAFT all) │
    │    3. Pisz maile (ANALYZED → DRAFTED)                   │
    │    4. Research (NEW → ANALYZED)                          │
    │    5. Scout jeśli pipeline < limit                      │
    │                                                         │
    │  POZA OKIENKIEM (20:00-8:00):                           │
    │    1. Higiena (inbox + follow-upy)                      │
    │    2. Research (przygotowanie na jutro)                  │
    │    3. Pisz maile (przygotowanie na jutro)               │
    │    4. Scout jeśli pipeline < limit na jutro             │
    │    ⛔ NIE wysyłaj / NIE zapisuj draftów IMAP            │
    └─────────────────────────────────────────────────────────┘
    """
    async with semaphore:
        session = Session(engine)

        if not worker_id:
            worker_id = f"{socket.gethostname()}_worker_{client_id}"

        try:
            # 1. WERYFIKACJA STATUSU
            client = session.query(Client).filter(Client.id == client_id).first()
            if not client or client.status != "ACTIVE":
                return False

            if PHASE2_ENABLED:
                queue_manager.register_worker(worker_id, client.id, "checking_limits")

            # 2. LIMIT I PIPELINE
            limit = calculate_daily_limit(client)
            done_today = get_today_progress(session, client)
            pipeline = _get_pipeline_counts(session, client)
            in_window = _is_sending_window()
            sending_mode = getattr(client, "sending_mode", "DRAFT")

            total_in_pipeline = pipeline["new"] + pipeline["analyzed"] + pipeline["drafted"]
            need_more = (done_today + total_in_pipeline) < limit

            # FAZA 0: HIGIENA (zawsze — inbox + follow-upy)
            await _handle_hygiene(session, client, use_queues)

            # =====================================================
            # OKIENKO WYSYŁKOWE (8:00 - 20:00)
            # =====================================================
            if in_window:
                # --- FAZA 1: WYSYŁKA / DRAFTY ---
                if done_today < limit:
                    if await _handle_drafts(session, client, worker_id, use_queues):
                        return True

                # --- FAZA 2: PISANIE (ANALYZED → DRAFTED) ---
                if pipeline["analyzed"] > 0:
                    if await _handle_writing(session, client, worker_id, use_queues):
                        return True

                # --- FAZA 3: RESEARCH (NEW → ANALYZED) ---
                if pipeline["new"] > 0:
                    if await _handle_research(session, client, worker_id, use_queues):
                        return True

                # --- FAZA 4: SCOUTING (jeśli pipeline za mały) ---
                if need_more:
                    if await _handle_scouting(session, client, worker_id):
                        return True

            # =====================================================
            # POZA OKIENKIEM (20:00 - 8:00) — przygotowanie na jutro
            # =====================================================
            else:
                logger.debug(f"[{client.name}] Poza okienkiem wysyłkowym — tryb przygotowania")

                # Czy mamy wystarczająco leadów na jutro?
                tomorrow_pipeline = pipeline["new"] + pipeline["analyzed"] + pipeline["drafted"]
                tomorrow_need = limit - tomorrow_pipeline

                # --- Research (NEW → ANALYZED) ---
                if pipeline["new"] > 0:
                    if await _handle_research(session, client, worker_id, use_queues):
                        return True

                # --- Pisanie (ANALYZED → DRAFTED) — przygotowujemy gotowe maile ---
                if pipeline["analyzed"] > 0:
                    if await _handle_writing(session, client, worker_id, use_queues):
                        return True

                # --- Scouting (jeśli brakuje leadów na jutro) ---
                if tomorrow_need > 0:
                    if await _handle_scouting(session, client, worker_id):
                        return True

            if PHASE2_ENABLED:
                queue_manager.register_worker(worker_id, client.id, "idle")

            return False

        except Exception as e:
            logger.error(f"💥 WORKER ERROR [Client {client_id}]: {e}", exc_info=True)
            if PHASE2_ENABLED:
                try:
                    queue_manager.register_worker(worker_id, client_id, "error")
                except Exception:
                    pass
            return False
        finally:
            session.close()


# ---------------------------------------------------------------------------
# RDZEŃ SYSTEMU
# ---------------------------------------------------------------------------

async def nexus_core_loop():
    """
    RDZEŃ SYSTEMU - NEXUS ENGINE v3.0
    Dispatcher zarządzający pulą workerów dla wszystkich aktywnych klientów.
    """
    console.clear()
    console.rule("[bold magenta]⚡ NEXUS ENGINE: PHASE 2 READY v3.0[/bold magenta]")
    logger.info("System startup. Max Workers: %s", MAX_CONCURRENT_AGENTS)

    if PHASE2_ENABLED:
        console.print(
            f"[bold green]✨ Phase 2 Active:[/bold green] "
            f"Queues={'ON' if USE_QUEUES else 'OFF'}, Rate Limiting=ON, Caching=ON"
        )
    else:
        console.print("[yellow]⚠️  Running in Legacy Mode (Phase 2 disabled)[/yellow]")

    active_tasks: Dict[int, asyncio.Task] = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)

    last_backup_time = datetime.now()
    last_sync_time = datetime.now()
    last_stats_time = datetime.now()

    logger.info("💾 Uruchamiam backup startowy...")
    await asyncio.to_thread(backup_manager.perform_backup)

    logger.info("🔄 Synchronizuję briefs z PayloadCMS...")
    with Session(engine) as sync_session:
        sync_result = await asyncio.to_thread(sync_briefs_to_clients, sync_session)
        _log_sync_result(sync_result)

    if PHASE2_ENABLED and USE_QUEUES:
        logger.info("📥 Populating queues from database...")
        await _populate_queues_from_db()

    while True:
        try:
            now = datetime.now()

            # BACKUP CO 6 GODZIN
            if (now - last_backup_time).total_seconds() > BACKUP_INTERVAL_SECONDS:
                logger.info("💾 Czas na cykliczny backup...")
                await asyncio.to_thread(backup_manager.perform_backup)
                last_backup_time = now

            # BRIEF SYNC CO 30 MINUT (wykrywanie zmian w Payload)
            if (now - last_sync_time).total_seconds() > BRIEF_SYNC_INTERVAL:
                logger.info("🔄 Sprawdzam zmiany w briefach...")
                with Session(engine) as sync_session:
                    sync_result = await asyncio.to_thread(sync_briefs_to_clients, sync_session)
                    _log_sync_result(sync_result)
                last_sync_time = now

            # STATYSTYKI CO 5 MINUT (Phase 2)
            if PHASE2_ENABLED and (now - last_stats_time).total_seconds() > STATS_INTERVAL:
                _print_system_stats()
                last_stats_time = now

            # POBRANIE AKTYWNYCH KLIENTÓW
            with Session(engine) as session:
                active_clients = session.query(Client.id, Client.name).filter(
                    Client.status == "ACTIVE"
                ).all()
                active_client_ids = {c.id for c in active_clients}

            # SPRZĄTANIE ZAKOŃCZONYCH ZADAŃ
            for cid in list(active_tasks.keys()):
                task = active_tasks[cid]
                if task.done():
                    if task.exception():
                        logger.error(f"Task for Client {cid} crashed: {task.exception()}")
                    del active_tasks[cid]

            # ANULOWANIE NIEAKTYWNYCH KLIENTÓW
            for cid in list(active_tasks.keys()):
                if cid not in active_client_ids:
                    active_tasks[cid].cancel()
                    del active_tasks[cid]

            # SPAWN NOWYCH ZADAŃ
            spawned_count = 0
            for cid in active_client_ids:
                if cid not in active_tasks:
                    wid = f"{socket.gethostname()}_worker_{cid}"
                    task = asyncio.create_task(
                        run_client_cycle(cid, semaphore, worker_id=wid, use_queues=USE_QUEUES)
                    )
                    active_tasks[cid] = task
                    spawned_count += 1

            if spawned_count > 0:
                logger.info(
                    f"Dispatcher spawned {spawned_count} new tasks. Active: {len(active_tasks)}"
                )

            await asyncio.sleep(DISPATCHER_INTERVAL)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.critical(f"🔥 DISPATCHER LOOP ERROR: {e}", exc_info=True)
            await asyncio.sleep(5)


async def run_forever():
    """WATCHDOG: Nieśmiertelna pętla restartująca system w razie krytycznej awarii."""
    while True:
        try:
            await nexus_core_loop()
        except KeyboardInterrupt:
            console.print("\n[bold red]🛑 Zatrzymano silnik NEXUS (Manual Stop).[/bold red]")
            if PHASE2_ENABLED:
                logger.info("🧹 Cleaning up Phase 2 resources...")
                try:
                    for worker in queue_manager.get_active_workers():
                        queue_manager.unregister_worker(worker["worker_id"])
                    logger.info("✅ Workers cleaned up")
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
            break
        except Exception as e:
            console.print(f"[bold red]💀 CRITICAL SYSTEM CRASH: {e}[/bold red]")
            logger.critical("SYSTEM CRASHED. RESTARTING IN 10s...", exc_info=True)
            await asyncio.sleep(10)
            console.print("[bold green]♻️  SYSTEM REBOOT...[/bold green]")


# ---------------------------------------------------------------------------
# HELPERY PHASE 2
# ---------------------------------------------------------------------------

async def _populate_queues_from_db() -> None:
    """Wypełnia kolejki Redis danymi z bazy po restarcie systemu."""
    if not PHASE2_ENABLED:
        return

    with Session(engine) as session:
        new_leads = session.query(Lead.id).filter(Lead.status == "NEW").limit(100).all()
        for lead in new_leads:
            queue_manager.push_lead(lead.id, QueueType.NEW)

        analyzed = session.query(Lead.id).filter(Lead.status == "ANALYZED").limit(50).all()
        for lead in analyzed:
            queue_manager.push_lead(lead.id, QueueType.ANALYZED)

        drafted = session.query(Lead.id).filter(Lead.status == "DRAFTED").limit(20).all()
        for lead in drafted:
            queue_manager.push_lead(lead.id, QueueType.DRAFTED)

        logger.info(
            f"📥 Queues populated: {len(new_leads)} new, "
            f"{len(analyzed)} analyzed, {len(drafted)} drafted"
        )


def _print_system_stats() -> None:
    """Drukuje tabelę statystyk systemu (co STATS_INTERVAL sekund)."""
    if not PHASE2_ENABLED:
        return

    try:
        from rich.table import Table

        cache_stats = cache_manager.get_cache_stats()
        queue_stats = queue_manager.get_queue_stats()
        rate_stats = rate_limiter.get_rate_limit_stats()

        table = Table(title="🎯 PHASE 2 STATISTICS", show_header=True)
        table.add_column("Category", style="cyan")
        table.add_column("Metric", style="yellow")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Cache", "Emails cached", str(cache_stats.get("emails_cached", 0)))
        table.add_row("Cache", "Companies cached", str(cache_stats.get("companies_cached", 0)))
        table.add_row("Cache", "Campaigns tracked", str(cache_stats.get("campaigns_tracked", 0)))
        table.add_row("Queues", "Total pending", str(queue_stats.get("total_pending", 0)))
        table.add_row("Queues", "Processing", str(queue_stats.get("processing", 0)))
        table.add_row("Queues", "Active workers", str(queue_stats.get("active_workers", 0)))
        table.add_row("Rate Limit", "Emails today (global)", str(rate_stats.get("global_daily_emails", 0)))
        table.add_row("Rate Limit", "SendGrid usage", f"{rate_stats.get('sendgrid_usage_percent', 0)}%")

        console.print("\n")
        console.print(table)
        console.print("\n")

    except Exception as e:
        logger.error(f"Stats printing error: {e}")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        pass
