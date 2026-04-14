from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sys
import os
import signal
import subprocess
import time
import asyncio
import decimal
import logging
from typing import Dict, Any, List, Optional

from fastapi import Security, HTTPException, status, Query
from fastapi.security.api_key import APIKeyHeader

# Setup ścieżek
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

PID_FILE = os.path.join(ROOT_DIR, 'engine.pid')
LOG_FILE = os.path.join(ROOT_DIR, 'engine.log')
HEARTBEAT_FILE = os.path.join(ROOT_DIR, 'engine.heartbeat')
_HEARTBEAT_TIMEOUT = 60
_ENGINE_START_GRACE = 120

# ---------------------------------------------------------------------------
# LOGGING — produkcyjne logi aplikacji + wyciszenie health-check spamu
# ---------------------------------------------------------------------------

# Filtr wyciszający powtarzalne endpointy pollingowe z access logów uvicorn
class HealthCheckFilter(logging.Filter):
    """Filtruje logi GET /api/metrics i /api/engine/status — polling co sekundę."""
    _SUPPRESSED_PATHS = ("/api/metrics", "/api/engine/status")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(path in msg for path in self._SUPPRESSED_PATHS)

# Aplikujemy filtr na logger uvicorn.access
uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.addFilter(HealthCheckFilter())

# Logger aplikacji — widoczny w docker logs
logger = logging.getLogger("nexus_api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_handler)

# Baza danych i inne
from app.database import SessionLocal, Client, Campaign, Lead, GlobalCompany, Base, engine, LeadFeedback, ClientAlignment, AlignmentHistory
from sqlalchemy import func

app = FastAPI(title="Nexus Engine API", description="Control API for Titan Bot Engine")

@app.on_event("startup")
def on_startup():
    """Auto-create all database tables if they don't exist."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[STARTUP] Tabele bazy danych zweryfikowane/utworzone")
    except Exception as e:
        logger.warning(f"[STARTUP] Problem z inicjalizacją DB: {e}")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4321",
        "http://localhost:3000",
        "https://nexusagent.pl",
        "https://www.nexusagent.pl",
        "https://panel.nexusagent.pl"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_NAME = "X-Nexus-Api-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key_header: str = Security(api_key_header)):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
    expected_key = os.getenv("NEXUS_ADMIN_KEY")
    
    if not expected_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Brak NEXUS_ADMIN_KEY na serwerze.")
        
    if api_key_header == expected_key:
        return api_key_header
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nieważny klucz API Nexus")


# ==============================================================================
# ENGINE MANAGEMENT
# ==============================================================================

def is_engine_running() -> bool:
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        try: os.remove(PID_FILE)
        except: pass
        try:
            if os.path.exists(HEARTBEAT_FILE): os.remove(HEARTBEAT_FILE)
        except: pass
        return False

    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, 'r') as f:
                ts = float(f.read().strip())
            if time.time() - ts > _HEARTBEAT_TIMEOUT:
                return False
            return True
        except (OSError, ValueError):
            pass

    try:
        pid_age = time.time() - os.path.getmtime(PID_FILE)
        return pid_age < _ENGINE_START_GRACE
    except Exception:
        return True


def start_engine_logic():
    if is_engine_running():
        return
    for f in (PID_FILE, HEARTBEAT_FILE):
        if os.path.exists(f):
            try: os.remove(f)
            except: pass
            
    try:
        from app import critical_monitor
        critical_monitor.clear_stop()
    except:
        pass

    try: open(LOG_FILE, 'w').close()
    except: pass

    log_handle = open(LOG_FILE, "a")
    process = subprocess.Popen(
        [sys.executable, "-u", "main.py"],
        cwd=ROOT_DIR,
        stdout=log_handle,
        stderr=log_handle,
    )
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
        logger.info(f"[ENGINE] Silnik uruchomiony (PID: {process.pid})")
    except Exception as e:
        logger.error(f"[ENGINE] Błąd zapisu PID: {e}")


def stop_engine_logic():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            logger.info(f"[ENGINE] Silnik zatrzymany (PID: {pid})")
        except Exception as e:
            logger.error(f"[ENGINE] Błąd zatrzymywania silnika: {e}")
        finally:
            try: os.remove(PID_FILE)
            except: pass

    if os.path.exists(HEARTBEAT_FILE):
        try: os.remove(HEARTBEAT_FILE)
        except: pass


def get_engine_logs(lines=200):
    if not os.path.exists(LOG_FILE): return "Brak logów."
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            recent = all_lines[-lines:]
            recent.reverse()
            return "".join(recent)
    except:
        return "Błąd odczytu."


@app.get("/api/engine/status")
def engine_status(api_key: str = Security(get_api_key)):
    running = is_engine_running()
    stopped = False
    stop_reason = ""
    if not running:
        try:
            from app import critical_monitor
            stopped, stop_reason = critical_monitor.is_stopped()
        except:
            pass
            
    return {
        "running": running,
        "critical_stop": stopped,
        "stop_reason": stop_reason,
    }


@app.post("/api/engine/start")
def start_engine(api_key: str = Security(get_api_key)):
    logger.info("[ENGINE] Żądanie uruchomienia silnika")
    start_engine_logic()
    return {"status": "started"}


@app.post("/api/engine/stop")
def stop_engine(api_key: str = Security(get_api_key)):
    logger.info("[ENGINE] Żądanie zatrzymania silnika")
    stop_engine_logic()
    return {"status": "stopped"}


@app.post("/api/engine/sync_briefs")
def sync_briefs(api_key: str = Security(get_api_key)):
    from app.brief_sync import sync_briefs_to_clients
    logger.info("[SYNC] Synchronizacja briefów...")
    try:
        with SessionLocal() as session:
            result = sync_briefs_to_clients(session)
        logger.info(f"[SYNC] Synchronizacja zakończona: {result}")
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"[SYNC] Błąd synchronizacji: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ==============================================================================
# STEROWANIE MANUALNE (Scout / Analyze / Write / Send)
# ==============================================================================

@app.post("/api/engine/manual/{action}")
async def trigger_manual_action(action: str, background_tasks: BackgroundTasks, client_id: int = Query(...), api_key: str = Security(get_api_key)):
    from app.agents.strategy import generate_strategy
    from app.agents.scout import run_scout_async
    from app.agents.researcher import analyze_lead
    from app.agents.writer import generate_email
    from app.scheduler import process_followups, save_draft_via_imap
    from app.tools import verify_sender_dns

    # Weryfikacja wstępna z szybką sesją
    with SessionLocal() as session:
        client = session.query(Client).get(client_id)
        if not client: raise HTTPException(status_code=404, detail="Brak klienta")
        logger.info(f"[MANUAL] Akcja '{action}' dla klienta #{client_id} ({client.name})")

        if action == "scout":
            camp = session.query(Campaign).filter(Campaign.client_id == client.id, Campaign.status == "ACTIVE").first()
            if not camp:
                return {"status": "error", "message": "Brak aktywnego wektora kampanii."}
            logger.info(f"[MANUAL:SCOUT] Generuję strategię dla kampanii #{camp.id}...")
            strategy = generate_strategy(client, camp.strategy_prompt, camp.id, session=session)
            if strategy and strategy.search_queries:
                def run_scout_bg(c_id, s):
                    with SessionLocal() as bg_session:
                        asyncio.run(run_scout_async(bg_session, c_id, s))
                # Odpalenie scouta bez blokowania pętli
                background_tasks.add_task(run_scout_bg, camp.id, strategy)
                return {"status": "success", "message": "Scout odpalony w tle."}
            return {"status": "error", "message": "Strategia nie wygenerowała zapytań."}

        elif action == "analyze":
            def run_analyze_bg(c_id):
                with SessionLocal() as bg_session:
                    leads = bg_session.query(Lead).join(Campaign).filter(Campaign.client_id == c_id, Lead.status == "NEW").limit(5).all()
                    for i, l in enumerate(leads, 1):
                        logger.info(f"[BG:ANALYZE] lead #{l.id}...")
                        try:
                            analyze_lead(bg_session, l.id)
                        except Exception as e:
                            logger.error(f"[BG:ANALYZE] błąd #{l.id}: {e}", exc_info=True)
            background_tasks.add_task(run_analyze_bg, client.id)
            return {"status": "success", "message": f"Zlecono do analizy w tle (max 5)."}

        elif action == "write":
            def run_write_bg(c_id):
                with SessionLocal() as bg_session:
                    leads = bg_session.query(Lead).join(Campaign).filter(Campaign.client_id == c_id, Lead.status == "ANALYZED").limit(5).all()
                    for i, l in enumerate(leads, 1):
                        logger.info(f"[BG:WRITE] lead #{l.id}...")
                        try:
                            generate_email(bg_session, l.id)
                        except Exception as e:
                            logger.error(f"[BG:WRITE] błąd #{l.id}: {e}", exc_info=True)
            background_tasks.add_task(run_write_bg, client.id)
            return {"status": "success", "message": f"Zlecono do wygenerowania maili w tle (max 5)."}

        elif action == "send":
            if client.smtp_user and "@" in client.smtp_user:
                domain = client.smtp_user.split("@")[1]
                dns_status = verify_sender_dns(domain)
                if not dns_status.get("spf_ok") or not dns_status.get("dmarc_ok"):
                    logger.error(f"[MANUAL:SEND] Blokada DNS: {domain}")
                    return {"status": "error", "message": f"Blokada Antyspamowa DNS dla {domain}"}
            
            def run_send_bg(c_id):
                with SessionLocal() as bg_session:
                    c = bg_session.query(Client).get(c_id)
                    process_followups(bg_session, c)
                    leads = bg_session.query(Lead).join(Campaign).filter(Campaign.client_id == c.id, Lead.status == "DRAFTED").limit(5).all()
                    from sqlalchemy import func as sqlfunc
                    for i, l in enumerate(leads, 1):
                        try:
                            logger.info(f"[BG:SEND] lead #{l.id}...")
                            save_draft_via_imap(l, c)
                            l.status = "SENT"
                            l.sent_at = sqlfunc.now()
                            bg_session.commit()
                        except Exception as e:
                            logger.error(f"[BG:SEND] błąd #{l.id}: {e}")
            background_tasks.add_task(run_send_bg, client.id)
            return {"status": "success", "message": f"Wysyłka (max 5) i FUP odpalone w tle."}

        elif action == "teacher":
            from app.agents.teacher import run_teacher_synthesis
            pending_count = (
                session.query(LeadFeedback)
                .join(Lead, LeadFeedback.lead_id == Lead.id)
                .join(Campaign, Lead.campaign_id == Campaign.id)
                .filter(Campaign.client_id == client_id, LeadFeedback.is_processed == False)
                .count()
            )
            if pending_count == 0:
                return {"status": "success", "message": "Brak nowych feedbacków do syntezy."}

            def run_teacher_bg(c_id):
                with SessionLocal() as bg_session:
                    logger.info(f"[BG:TEACHER] Synteza wiedzy klient #{c_id}...")
                    try:
                        result = run_teacher_synthesis(bg_session, c_id)
                        if result.get("success"):
                            logger.info(
                                f"[BG:TEACHER] OK — v{result.get('version')}, "
                                f"{result.get('feedbacks_processed')} feedbacków"
                            )
                        else:
                            logger.error(f"[BG:TEACHER] Błąd: {result.get('error')}")
                    except Exception as e:
                        logger.error(f"[BG:TEACHER] Exception: {e}", exc_info=True)
            background_tasks.add_task(run_teacher_bg, client.id)
            return {"status": "success", "message": f"Teacher uruchomiony w tle ({pending_count} feedbacków)."}

        logger.warning(f"[MANUAL] Nieznana akcja: '{action}'")
        return {"status": "error", "message": "Nieznana akcja manualna."}


# ==============================================================================
# LOGI + WEBSOCKET
# ==============================================================================

@app.get("/api/engine/logs")
def engine_logs(lines: int = 200, api_key: str = Security(get_api_key)):
    return {"logs": get_engine_logs(lines)}


@app.websocket("/api/ws/logs")
async def websocket_logs(websocket: WebSocket, token: str = Query(None)):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
    expected_key = os.getenv("NEXUS_ADMIN_KEY")
    
    if not token or token != expected_key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await websocket.accept()
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("")
            
    log_file = open(LOG_FILE, "r", encoding="utf-8")
    log_file.seek(0, 2)
    
    try:
        while True:
            line = log_file.readline()
            if not line:
                # Sprawdź czy plik nie został obcięty (engine restart)
                current_pos = log_file.tell()
                file_size = os.path.getsize(LOG_FILE)
                if current_pos > file_size:
                    # Plik został obcięty — wracamy na początek
                    log_file.seek(0)
                await asyncio.sleep(0.5)
                continue
            await websocket.send_text(line)
    except WebSocketDisconnect:
        pass
    finally:
        log_file.close()


# ==============================================================================
# METRYKI GLOBALNE
# ==============================================================================

@app.get("/api/metrics")
def get_metrics(api_key: str = Security(get_api_key)):
    try:
        with SessionLocal() as session:
            c_new = session.query(Lead).filter(Lead.status == "NEW").count()
            c_ready = session.query(Lead).filter(Lead.status == "ANALYZED").count()
            c_draft = session.query(Lead).filter(Lead.status == "DRAFTED").count()
            today = time.strftime('%Y-%m-%d')
            sent_today = session.query(Lead).filter(
                Lead.status == "SENT",
                func.date(Lead.sent_at) == today
            ).count()
            
        return {
            "queue_new": c_new,
            "queue_analyzed": c_ready,
            "queue_drafted": c_draft,
            "sent_today": sent_today
        }
    except Exception:
        return {"queue_new": 0, "queue_analyzed": 0, "queue_drafted": 0, "sent_today": 0}


# Per-client metrics (z warmup)
@app.get("/api/metrics/{client_id}")
def get_client_metrics(client_id: int, api_key: str = Security(get_api_key)):
    try:
        from app.warmup import calculate_daily_limit
        with SessionLocal() as session:
            client = session.query(Client).get(client_id)
            if not client:
                raise HTTPException(status_code=404, detail="Brak klienta")
            
            c_new = session.query(Lead).join(Campaign).filter(Campaign.client_id == client_id, Lead.status == "NEW").count()
            c_ready = session.query(Lead).join(Campaign).filter(Campaign.client_id == client_id, Lead.status == "ANALYZED").count()
            c_draft = session.query(Lead).join(Campaign).filter(Campaign.client_id == client_id, Lead.status == "DRAFTED").count()
            
            today = time.strftime('%Y-%m-%d')
            sent_today = session.query(Lead).join(Campaign).filter(
                Campaign.client_id == client_id,
                Lead.status == "SENT",
                func.date(Lead.sent_at) == today
            ).count()
            
            eff_limit = calculate_daily_limit(client)
            target = client.daily_limit or 50
            is_warmup = client.warmup_enabled and eff_limit < target
        
        return {
            "queue_new": c_new,
            "queue_analyzed": c_ready,
            "queue_drafted": c_draft,
            "sent_today": sent_today,
            "effective_limit": eff_limit,
            "target_limit": target,
            "is_warmup": is_warmup,
        }
    except Exception:
        return {"queue_new": 0, "queue_analyzed": 0, "queue_drafted": 0, "sent_today": 0, "effective_limit": 0, "target_limit": 50, "is_warmup": False}


# ==============================================================================
# KLIENCI — CRUD KOMPLETNY
# ==============================================================================

class ClientCreate(BaseModel):
    name: str
    industry: str
    sender_name: str
    mode: str
    smtp_server: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    value_proposition: str
    ideal_customer_profile: str
    privacy_policy_url: str | None = None
    html_footer: str | None = None

class ClientUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    sender_name: str | None = None
    mode: str | None = None
    sending_mode: str | None = None
    value_proposition: str | None = None
    ideal_customer_profile: str | None = None
    tone_of_voice: str | None = None
    negative_constraints: str | None = None
    case_studies: str | None = None
    # Konfiguracja Techniczna
    smtp_server: str | None = None
    imap_server: str | None = None
    smtp_port: int | None = None
    imap_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    daily_limit: int | None = None
    html_footer: str | None = None
    privacy_policy_url: str | None = None
    # Warmup
    warmup_enabled: bool | None = None
    warmup_start_limit: int | None = None
    warmup_increment: int | None = None
    # Modele AI
    scout_model: str | None = None
    researcher_model: str | None = None
    writer_model: str | None = None
    teacher_model: str | None = None
    # Gatekeeper
    gatekeeper_strictness: str | None = None  # strict / balanced / permissive

@app.get("/api/clients")
def get_clients(api_key: str = Security(get_api_key)):
    try:
        with SessionLocal() as session:
            clients = session.query(Client).all()
            return [{
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "mode": c.mode,
                "sending_mode": c.sending_mode,
                "leads_assigned": sum(1 for camp in c.campaigns for _ in camp.leads)
            } for c in clients]
    except Exception:
        return []

@app.get("/api/clients/{client_id}")
def get_client(client_id: int, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        c = session.query(Client).get(client_id)
        if not c:
            raise HTTPException(status_code=404, detail="Klient nie istnieje")
        # Zwracamy wszystkie kolumny BEZ hasła SMTP
        data = {col.name: getattr(c, col.name) for col in c.__table__.columns if col.name != "smtp_password"}
        # Dodaj info o haśle (czy istnieje)
        data["has_smtp_password"] = bool(c.smtp_password)
        # Serializacja datetime
        for k, v in data.items():
            if hasattr(v, 'isoformat'):
                data[k] = v.isoformat()
        return data

@app.post("/api/clients")
def create_client(payload: ClientCreate, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        from app.kms_client import encrypt_credential
        encrypted_pass = encrypt_credential(payload.smtp_password) if payload.smtp_password else ""
        nc = Client(
            name=payload.name, industry=payload.industry, sender_name=payload.sender_name,
            value_proposition=payload.value_proposition, ideal_customer_profile=payload.ideal_customer_profile,
            mode=payload.mode,
            sending_mode="DRAFT",
            smtp_server=payload.smtp_server, smtp_port=payload.smtp_port, smtp_user=payload.smtp_user,
            smtp_password=encrypted_pass, html_footer=payload.html_footer, status="ACTIVE",
            privacy_policy_url=payload.privacy_policy_url
        )
        session.add(nc)
        session.commit()
        return {"status": "success", "id": nc.id}

@app.put("/api/clients/{client_id}")
def update_client(client_id: int, payload: ClientUpdate, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        c = session.query(Client).get(client_id)
        if not c:
            raise HTTPException(status_code=404, detail="Klient nie znany")
            
        update_data = payload.dict(exclude_unset=True)
        
        # Obsługa hasła SMTP — szyfrowanie KMS
        if "smtp_password" in update_data:
            if update_data["smtp_password"]:
                from app.kms_client import encrypt_credential
                c.smtp_password = encrypt_credential(update_data.pop("smtp_password"))
            else:
                update_data.pop("smtp_password")
        
        # Obsługa warmup — ustawienie daty startu
        if "warmup_enabled" in update_data and update_data["warmup_enabled"] and not c.warmup_enabled:
            from datetime import datetime
            c.warmup_started_at = datetime.now()

        for key, value in update_data.items():
            setattr(c, key, value)
            
        session.commit()
        return {"status": "success"}


# Toggle statusu ACTIVE/PAUSED
@app.post("/api/clients/{client_id}/toggle-status")
def toggle_client_status(client_id: int, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        c = session.query(Client).get(client_id)
        if not c:
            raise HTTPException(status_code=404, detail="Klient nie znany")
        c.status = "PAUSED" if c.status == "ACTIVE" else "ACTIVE"
        session.commit()
        return {"status": "success", "new_status": c.status}


# ==============================================================================
# KRS FOOTER GENERATOR
# ==============================================================================

class KrsFooterRequest(BaseModel):
    nip: str
    website: str
    phone: str
    email: str

@app.post("/api/clients/{client_id}/generate-krs-footer")
def generate_krs_footer(client_id: int, payload: KrsFooterRequest, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        c = session.query(Client).get(client_id)
        if not c:
            raise HTTPException(status_code=404, detail="Klient nie znany")
        
        from app.krs_api import generate_full_legal_footer
        res = generate_full_legal_footer(payload.nip)
        if not res.get("success"):
            return {"status": "error", "message": res.get("error_message")}
            
        c.nip = payload.nip
        brand_name = c.name
        legal_name = res.get('name') or c.name
        c.legal_name = legal_name 
        
        footer_html = f"""<br/><br/>
<table style="font-family: Arial, sans-serif; font-size: 13px; color: #333; border-collapse: collapse;">
  <tr>
    <td style="padding-right: 15px; border-right: 2px solid #0066cc;">
      <strong style="color: #0066cc; font-size: 14px;">{brand_name}</strong><br/>
      {legal_name}
    </td>
    <td style="padding-left: 15px;">
      📞 <a href="tel:{payload.phone.replace(' ', '')}" style="color: #333; text-decoration: none;">{payload.phone}</a><br/>
      📧 <a href="mailto:{payload.email}" style="color: #0066cc;">{payload.email}</a><br/>
      🌐 <a href="https://{payload.website.replace('https://', '').replace('http://', '')}" style="color: #0066cc;">{payload.website.replace('https://', '').replace('http://', '')}</a>
    </td>
  </tr>
  <tr>
    <td colspan="2" style="padding-top: 10px; font-size: 10px; color: #666; line-height: 1.3;">
      {res.get('address') or 'Brak adresu'}<br/>
      {res.get('sad_rejonowy')}<br/>
      KRS: {res.get('krs') or payload.nip} | NIP: {res.get('nip') or payload.nip} | REGON: {res.get('regon') or '...'}<br/>
      Kapitał zakładowy: {res.get('kapital_zakladowy')} PLN
    </td>
  </tr>
</table>"""
        c.html_footer = footer_html
        session.commit()
        return {"status": "success", "html": footer_html}


# ==============================================================================
# MODELE AI — Lista dostępnych modeli i kluczy
# ==============================================================================

@app.get("/api/models")
def get_models(api_key: str = Security(get_api_key)):
    try:
        from app.model_factory import get_available_models, get_available_api_keys, DEFAULT_MODEL
        return {
            "models": get_available_models("all"),
            "api_keys": get_available_api_keys(),
            "default_model": DEFAULT_MODEL,
        }
    except ImportError:
        return {"models": [], "api_keys": {}, "default_model": "gemini-3.1-flash-lite-preview"}


# ==============================================================================
# KAMPANIE — CRUD
# ==============================================================================

class CampaignCreate(BaseModel):
    client_id: int
    strategy_prompt: str

@app.get("/api/campaigns")
def get_campaigns(api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        campaigns = session.query(Campaign).filter(Campaign.status == "ACTIVE").order_by(Campaign.id.desc()).all()
        return [{
            "id": c.id,
            "client_id": c.client_id,
            "strategy_prompt": c.strategy_prompt,
            "leads_count": len(c.leads)
        } for c in campaigns]

@app.post("/api/campaigns")
def create_campaign(payload: CampaignCreate, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        nc = Campaign(client_id=payload.client_id, name="Auto", status="ACTIVE", strategy_prompt=payload.strategy_prompt)
        session.add(nc)
        session.commit()
        return {"status": "success", "id": nc.id}

@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        c = session.query(Campaign).get(campaign_id)
        if c:
            c.status = "ARCHIVED"
            session.commit()
        return {"status": "success"}


# ==============================================================================
# LEADY — Tabela + Kanban + Draft Preview
# ==============================================================================

@app.get("/api/leads/{client_id}")
def get_leads(
    client_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_field: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    api_key: str = Security(get_api_key),
):
    from sqlalchemy import or_
    from datetime import datetime

    with SessionLocal() as session:
        q = session.query(
            Lead.id, Lead.status, Lead.target_email, Lead.ai_confidence_score,
            Lead.generated_email_subject, Lead.step_number, Lead.sent_at,
            GlobalCompany.name.label("company_name"), GlobalCompany.domain
        ).join(GlobalCompany).join(Campaign).filter(
            Campaign.client_id == client_id
        )

        if status:
            q = q.filter(Lead.status == status.upper())

        if search:
            pattern = f"%{search}%"
            q = q.filter(or_(
                GlobalCompany.name.ilike(pattern),
                Lead.target_email.ilike(pattern),
                GlobalCompany.domain.ilike(pattern),
            ))

        if date_field in ("sent_at",) and (date_from or date_to):
            col = Lead.sent_at
            if date_from:
                try:
                    q = q.filter(col >= datetime.fromisoformat(date_from))
                except ValueError:
                    pass
            if date_to:
                try:
                    q = q.filter(col <= datetime.fromisoformat(date_to + "T23:59:59"))
                except ValueError:
                    pass

        total = q.count()
        rows = q.order_by(Lead.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return {
            "leads": [{
                "id": r.id,
                "status": r.status,
                "company_name": r.company_name,
                "domain": r.domain,
                "target_email": r.target_email,
                "confidence": r.ai_confidence_score,
                "subject": r.generated_email_subject,
                "step": r.step_number,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            } for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

@app.get("/api/leads/{client_id}/kanban")
def get_leads_kanban(client_id: int, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        statuses = ["NEW", "ANALYZED", "DRAFTED", "SENT"]
        result = {}
        for s in statuses:
            count = session.query(Lead).join(Campaign).filter(
                Campaign.client_id == client_id,
                Lead.status == s
            ).count()
            result[s] = count
        return result

@app.get("/api/leads/draft/{lead_id}")
def get_lead_draft(lead_id: int, api_key: str = Security(get_api_key)):
    with SessionLocal() as session:
        lead = session.query(Lead).get(lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead nie znaleziony")
        company = session.query(GlobalCompany).get(lead.global_company_id) if lead.global_company_id else None
        return {
            "id": lead.id,
            "company_name": company.name if company else "Nieznana",
            "domain": company.domain if company else "",
            "target_email": lead.target_email,
            "subject": lead.generated_email_subject,
            "body": lead.generated_email_body,
            "analysis": lead.ai_analysis_summary,
            "confidence": lead.ai_confidence_score,
            "status": lead.status,
            "step": lead.step_number,
        }


# ==============================================================================
# STATYSTYKI & ROI
# ==============================================================================

@app.get("/api/stats/{client_id}")
def get_client_stats(client_id: int, api_key: str = Security(get_api_key)):
    from app.stats_manager import get_all_time_totals
    with SessionLocal() as session:
        stats = get_all_time_totals(session, client_id)
        if not stats:
            return {
                "domains_scanned": 0, "domains_approved": 0, "emails_drafted": 0, "emails_sent": 0,
                "replies_total": 0, "replies_positive": 0, "reply_rate": 0, "positive_rate": 0,
                "bounces": 0, "dns_blocks": 0, "opt_outs": 0, "leads_analyzed": 0,
                "emails_found": 0, "avg_confidence_score": 0, "avg_response_time_hours": 0,
                "followup_step_2_sent": 0, "followup_step_3_sent": 0, "domains_rejected": 0,
                "domains_blacklisted": 0, "emails_verified": 0, "emails_rejected_freemail": 0,
                "replies_negative": 0, "replies_neutral": 0,
            }
        for k, v in stats.items():
            if isinstance(v, decimal.Decimal):
                stats[k] = float(v)
        return stats


# ==============================================================================
# PDF REPORT GENERATOR
# ==============================================================================

@app.post("/api/reports/{client_id}/generate")
def generate_report(client_id: int, api_key: str = Security(get_api_key)):
    from app.agents.reporter import create_pdf_report
    logger.info(f"[REPORT] Generuję raport PDF dla klienta #{client_id}...")
    with SessionLocal() as session:
        try:
            pdf_path = create_pdf_report(session, client_id)
            if pdf_path and os.path.exists(pdf_path):
                logger.info(f"[REPORT] Raport wygenerowany: {os.path.basename(pdf_path)}")
                return {"status": "success", "path": pdf_path, "filename": os.path.basename(pdf_path)}
            logger.warning(f"[REPORT] Nie udało się wygenerować raportu dla klienta #{client_id}")
            return {"status": "error", "message": "Nie udało się wygenerować raportu."}
        except Exception as e:
            logger.error(f"[REPORT] Błąd generowania raportu: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

@app.get("/api/reports/download")
def download_report(path: str = Query(...), api_key: str = Security(get_api_key)):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Plik nie istnieje")
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


# ==============================================================================
# PHASE 2 — REDIS MONITORING (Cache, Rate Limits, Queue)
# ==============================================================================

@app.get("/api/phase2/status")
def phase2_status(api_key: str = Security(get_api_key)):
    try:
        from app.redis_client import redis_client
        connected = redis_client.ping()
        return {"enabled": True, "connected": connected}
    except ImportError:
        return {"enabled": False, "connected": False}

@app.get("/api/phase2/cache")
def phase2_cache(api_key: str = Security(get_api_key)):
    try:
        from app.cache_manager import cache_manager
        from app.tools import get_email_cache_stats
        cache_stats = cache_manager.get_cache_stats()
        email_stats = get_email_cache_stats()
        
        emails_cached = email_stats.get("total_cached", 0)
        companies_cached = cache_stats.get("companies_cached", 0)
        DEBOUNCE_COST = 0.25
        CRAWL4AI_COST = 0.0  # Crawl4AI = darmowy (lokalny headless browser)
        
        return {
            "cache_stats": cache_stats,
            "email_stats": email_stats,
            "cost_savings": {
                "email_savings": round(emails_cached * DEBOUNCE_COST, 2),
                "scraping_savings": 0.0,  # Crawl4AI jest darmowy
                "total_savings": round(emails_cached * DEBOUNCE_COST, 2),
            }
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/phase2/rate-limits")
def phase2_rate_limits(client_id: int = Query(None), api_key: str = Security(get_api_key)):
    try:
        from app.rate_limiter import rate_limiter
        from app.warmup import calculate_daily_limit
        
        stats = rate_limiter.get_rate_limit_stats()
        
        # Per-client data (jeśli podano)
        if client_id:
            with SessionLocal() as session:
                client = session.query(Client).get(client_id)
                if client:
                    stats["client_daily_sent"] = rate_limiter.get_emails_sent_today(client_id)
                    stats["client_daily_limit"] = calculate_daily_limit(client)
        
        return stats
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/phase2/queues")
def phase2_queues(api_key: str = Security(get_api_key)):
    try:
        from app.queue_manager import queue_manager
        stats = queue_manager.get_queue_stats()
        workers = queue_manager.get_active_workers()
        return {"queue_stats": stats, "workers": workers}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/phase2/reset-limits/{client_id}")
def phase2_reset_limits(client_id: int, api_key: str = Security(get_api_key)):
    try:
        from app.rate_limiter import rate_limiter
        rate_limiter.reset_client_limits(client_id)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ==============================================================================
# TEACHER ENGINE — Feedback, Alignment, Trigger, Rollback
# ==============================================================================

# --- FEEDBACK CRUD (pełne pola — laboratorium do oceniania) ---

class FeedbackCreate(BaseModel):
    researcher_rating: int | None = None       # 1-5
    writer_rating: int | None = None           # 1-5
    researcher_comments: str | None = None
    writer_comments: str | None = None
    corrected_subject: str | None = None
    corrected_body: str | None = None

class FeedbackUpdate(BaseModel):
    researcher_rating: int | None = None
    writer_rating: int | None = None
    researcher_comments: str | None = None
    writer_comments: str | None = None
    corrected_subject: str | None = None
    corrected_body: str | None = None


@app.post("/api/leads/feedback/{lead_id}")
def create_or_update_feedback(lead_id: int, payload: FeedbackCreate, api_key: str = Security(get_api_key)):
    """Tworzy lub aktualizuje feedback dla leada (upsert na lead_id)."""
    with SessionLocal() as session:
        lead = session.query(Lead).get(lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead nie znaleziony")

        fb = session.query(LeadFeedback).filter_by(lead_id=lead_id).first()
        if fb:
            update_data = payload.dict(exclude_unset=True)
            for key, value in update_data.items():
                setattr(fb, key, value)
            fb.is_processed = False  # Reset — Teacher musi ponownie przetworzyć
            logger.info(f"[FEEDBACK] Zaktualizowano feedback dla lead #{lead_id}")
        else:
            fb = LeadFeedback(lead_id=lead_id, **payload.dict(exclude_unset=True))
            session.add(fb)
            logger.info(f"[FEEDBACK] Nowy feedback dla lead #{lead_id}")

        session.commit()

        return {
            "status": "success",
            "feedback_id": fb.id,
            "lead_id": lead_id,
            "is_processed": fb.is_processed,
        }


@app.get("/api/leads/feedback/{lead_id}")
def get_feedback(lead_id: int, api_key: str = Security(get_api_key)):
    """Pobiera feedback dla leada ze wszystkimi polami."""
    with SessionLocal() as session:
        fb = session.query(LeadFeedback).filter_by(lead_id=lead_id).first()
        if not fb:
            return {"exists": False}

        lead = session.query(Lead).get(lead_id)
        company = None
        if lead and lead.global_company_id:
            company = session.query(GlobalCompany).get(lead.global_company_id)

        return {
            "exists": True,
            "id": fb.id,
            "lead_id": fb.lead_id,
            "researcher_rating": fb.researcher_rating,
            "writer_rating": fb.writer_rating,
            "researcher_comments": fb.researcher_comments,
            "writer_comments": fb.writer_comments,
            "corrected_subject": fb.corrected_subject,
            "corrected_body": fb.corrected_body,
            "is_processed": fb.is_processed,
            "created_at": fb.created_at.isoformat() if fb.created_at else None,
            "updated_at": fb.updated_at.isoformat() if fb.updated_at else None,
            # Kontekst leada (dla panelu)
            "original_subject": lead.generated_email_subject if lead else None,
            "original_body": lead.generated_email_body if lead else None,
            "company_name": company.name if company else None,
            "company_domain": company.domain if company else None,
            "analysis_summary": lead.ai_analysis_summary if lead else None,
            "confidence": lead.ai_confidence_score if lead else None,
            "status": lead.status if lead else None,
        }


@app.delete("/api/leads/feedback/{lead_id}")
def delete_feedback(lead_id: int, api_key: str = Security(get_api_key)):
    """Usuwa feedback dla leada."""
    with SessionLocal() as session:
        fb = session.query(LeadFeedback).filter_by(lead_id=lead_id).first()
        if not fb:
            raise HTTPException(status_code=404, detail="Feedback nie istnieje")
        session.delete(fb)
        session.commit()
        logger.info(f"[FEEDBACK] Usunięto feedback dla lead #{lead_id}")
        return {"status": "success"}


@app.get("/api/feedback/{client_id}")
def list_feedbacks(client_id: int, processed: bool | None = None, api_key: str = Security(get_api_key)):
    """Lista wszystkich feedbacków dla klienta. Filtr: ?processed=false dla oczekujących."""
    with SessionLocal() as session:
        query = (
            session.query(LeadFeedback)
            .join(Lead, LeadFeedback.lead_id == Lead.id)
            .join(Campaign, Lead.campaign_id == Campaign.id)
            .filter(Campaign.client_id == client_id)
        )
        if processed is not None:
            query = query.filter(LeadFeedback.is_processed == processed)

        feedbacks = query.order_by(LeadFeedback.updated_at.desc()).limit(100).all()

        result = []
        for fb in feedbacks:
            lead = session.query(Lead).get(fb.lead_id)
            company = None
            if lead and lead.global_company_id:
                company = session.query(GlobalCompany).get(lead.global_company_id)

            result.append({
                "id": fb.id,
                "lead_id": fb.lead_id,
                "researcher_rating": fb.researcher_rating,
                "writer_rating": fb.writer_rating,
                "researcher_comments": fb.researcher_comments,
                "writer_comments": fb.writer_comments,
                "corrected_subject": fb.corrected_subject,
                "corrected_body": fb.corrected_body,
                "is_processed": fb.is_processed,
                "created_at": fb.created_at.isoformat() if fb.created_at else None,
                "updated_at": fb.updated_at.isoformat() if fb.updated_at else None,
                "company_name": company.name if company else None,
                "original_subject": lead.generated_email_subject if lead else None,
                "status": lead.status if lead else None,
            })
        return result


# --- ALIGNMENT CRUD (Księga Zasad) ---

@app.get("/api/alignment/{client_id}")
def get_alignment(client_id: int, api_key: str = Security(get_api_key)):
    """Pobiera aktualną Księgę Zasad (ClientAlignment) ze wszystkimi polami."""
    with SessionLocal() as session:
        a = session.query(ClientAlignment).filter_by(client_id=client_id).first()
        if not a:
            return {"exists": False, "client_id": client_id}

        return {
            "exists": True,
            "client_id": a.client_id,
            "version": a.version,
            "strategy_guidelines": a.strategy_guidelines,
            "scouting_guidelines": a.scouting_guidelines,
            "research_guidelines": a.research_guidelines,
            "writing_guidelines": a.writing_guidelines,
            "gold_examples": a.gold_examples,
            "avg_rating_at_synthesis": a.avg_rating_at_synthesis,
            "feedbacks_processed_count": a.feedbacks_processed_count,
            "last_updated": a.last_updated.isoformat() if a.last_updated else None,
        }


@app.get("/api/alignment/{client_id}/history")
def get_alignment_history(client_id: int, api_key: str = Security(get_api_key)):
    """Lista archiwalnych wersji alignment (do rollbacku)."""
    with SessionLocal() as session:
        versions = (
            session.query(AlignmentHistory)
            .filter_by(client_id=client_id)
            .order_by(AlignmentHistory.archived_at.desc())
            .limit(10)
            .all()
        )
        return [{
            "id": v.id,
            "version": v.version,
            "strategy_guidelines_preview": (v.strategy_guidelines or "")[:200],
            "scouting_guidelines_preview": (v.scouting_guidelines or "")[:200],
            "research_guidelines_preview": (v.research_guidelines or "")[:200],
            "writing_guidelines_preview": (v.writing_guidelines or "")[:200],
            "gold_examples": v.gold_examples,
            "avg_rating_at_synthesis": v.avg_rating_at_synthesis,
            "archived_at": v.archived_at.isoformat() if v.archived_at else None,
        } for v in versions]


@app.post("/api/alignment/{client_id}/rollback")
def trigger_rollback(client_id: int, version: int | None = None, api_key: str = Security(get_api_key)):
    """Przywraca alignment do wybranej wersji archiwalnej."""
    from app.agents.teacher import rollback_alignment
    logger.info(f"[TEACHER] Rollback żądany dla klienta #{client_id}, target_version={version}")
    with SessionLocal() as session:
        result = rollback_alignment(session, client_id, target_version=version)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result


# --- TEACHER MANUAL TRIGGER ---

@app.post("/api/alignment/{client_id}/trigger")
def trigger_teacher(client_id: int, api_key: str = Security(get_api_key)):
    """Ręczne wymuszenie syntezy Teacher (bez debounce)."""
    from app.agents.teacher import run_teacher_synthesis
    logger.info(f"[TEACHER] Ręczne uruchomienie syntezy dla klienta #{client_id}")
    with SessionLocal() as session:
        result = run_teacher_synthesis(session, client_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Błąd syntezy"))
        logger.info(
            f"[TEACHER] Synteza zakończona: v{result.get('version')}, "
            f"{result.get('feedbacks_processed')} feedbacków"
        )
        return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
