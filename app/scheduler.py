# app/scheduler.py
"""
SCHEDULER - Follow-up & Draft Management
NOW WITH: Optional queue integration for follow-ups
"""

import sys
import os
import imaplib
import time
import mimetypes
import logging
import ctypes
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from email.message import EmailMessage
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.database import Lead, Client
from app.kms_client import decrypt_credential


def _secure_wipe(s: str) -> None:
    """Bezpieczne kasowanie referencji hasła. Samo del wystarczy — GC posprząta.
    UWAGA: Poprzednia wersja z ctypes.memset powodowała SIGSEGV (segfault)
    ponieważ nadpisywała immutable stringi Pythona w pamięci interpretera.
    """
    pass  # samo del zmiennej po wywołaniu wystarcza
from rich.console import Console

# NEW: Import queue manager (optional integration)
try:
    from app.queue_manager import queue_manager, QueueType
    QUEUE_ENABLED = True
except ImportError:
    QUEUE_ENABLED = False

console = Console()
logger = logging.getLogger("scheduler")

MAX_IMAP_RETRIES = 3
IMAP_RETRY_BACKOFF = [2, 5, 10]  # sekundy między próbami


def _detect_drafts_folder(mail) -> str:
    """
    Wykrywa folder draftów na serwerze IMAP.
    1. Szuka flagi systemowej \\Drafts (RFC 6154)
    2. Fallback na ręczne matching nazwy folderu
    """
    selected = "Drafts"
    try:
        status, folder_list_raw = mail.list()
        if status != 'OK':
            return selected

        # 1. RFC 6154: szukaj flagi \Drafts
        for folder_data in folder_list_raw:
            if not folder_data:
                continue
            f_str = folder_data.decode('utf-8', errors='ignore')
            if r'\Drafts' in f_str:
                parts = f_str.split(' "/" ')
                if len(parts) == 2:
                    selected = parts[1].strip('"')
                    logger.info(f"   📂 [IMAP] Wykryto folder draftów przez flagę: '{selected}'")
                    return selected

        # 2. Fallback na ręczne matchowanie nazw
        folders_to_try = [
            "Kopie robocze", "[Gmail]/Drafts", "Drafts", "Draft",
            "Szkice", "Wersje robocze", "INBOX.Drafts",
        ]
        f_list = str(folder_list_raw)
        for f in folders_to_try:
            if f'"{f}"' in f_list or f in f_list:
                selected = f
                logger.info(f"   📂 [IMAP] Folder draftów po nazwie: '{selected}'")
                return selected

    except Exception as e:
        logger.warning(f"   ⚠️ [IMAP] Błąd wykrywania folderu draftów: {e}")

    logger.info(f"   📂 [IMAP] Domyślny folder draftów: '{selected}'")
    return selected


def _imap_connect_and_login(client: Client):
    """
    Tworzy połączenie IMAP i loguje się.
    
    Strategia połączenia (kolejność prób):
    1. Port 143 + STARTTLS — odporny na blokady firewalla Purelymail na port 993
    2. Port 993 SSL — klasyczny backup
    
    Hasło odszyfrowywane z KMS tuż przed użyciem.
    """
    if not client.imap_server:
        raise RuntimeError("Brak konfiguracji IMAP")

    _imap_password = decrypt_credential(client.smtp_password or "")
    
    strategies = [
        ("143+STARTTLS", 143, False),
        ("993+SSL",      993, True),
    ]
    
    last_error = ""
    
    try:
        for label, port, use_ssl in strategies:
            mail = None
            try:
                if use_ssl:
                    mail = imaplib.IMAP4_SSL(client.imap_server, port, timeout=20)
                else:
                    mail = imaplib.IMAP4(client.imap_server, port, timeout=20)
                
                mail.socket().settimeout(60)
                
                # STARTTLS upgrade dla portu 143
                if not use_ssl and hasattr(mail, 'capabilities') and 'STARTTLS' in mail.capabilities:
                    mail.starttls()
                
                mail.login(client.smtp_user, _imap_password)
                logger.info(f"   ✅ [IMAP] Połączono przez {label}")
                return mail
                
            except Exception as e:
                last_error = f"{label}: {e}"
                logger.warning(f"   ⚠️ [IMAP] {label} nieudane: {e}")
                if mail:
                    try: mail.logout()
                    except: pass
                continue
        
        raise RuntimeError(f"Wszystkie strategie IMAP wyczerpane. Ostatni: {last_error}")
        
    finally:
        del _imap_password


def save_draft_via_imap(lead: Lead, client: Client):
    """
    Zapisuje draft na serwerze IMAP z retry logic (3 próby + backoff).
    
    Odporny na:
    - TLS/SSL EOF (niestabilne połączenia Purelymail)
    - Timeout na handshake lub append
    - Przejściowe awarie sieci
    
    Zwraca (True, info) lub (False, error_msg).
    """
    # --- 1. BUDOWANIE WIADOMOŚCI (raz, poza pętlą retry) ---
    msg = EmailMessage()
    msg["Subject"] = lead.generated_email_subject
    msg["From"] = f"{client.sender_name} <{client.smtp_user}>"

    if lead.target_email:
        msg["To"] = lead.target_email
    else:
        return False, "Brak adresu email."

    final_html_body = lead.generated_email_body

    soup = BeautifulSoup(final_html_body, "html.parser")
    text_content = soup.get_text(separator="\n", strip=True)
    msg.set_content(text_content)
    msg.add_alternative(final_html_body, subtype="html")

    # Załącznik (jeśli jest)
    if client.attachment_filename:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, 'files', client.attachment_filename)

        if os.path.exists(file_path):
            ctype, encoding = mimetypes.guess_type(file_path)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with open(file_path, 'rb') as f:
                msg.add_attachment(
                    f.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=client.attachment_filename,
                )
        else:
            console.print(
                f"[bold red]⚠️ BŁĄD ZAŁĄCZNIKA:[/bold red] "
                f"Nie znaleziono pliku '{client.attachment_filename}'"
            )

    if not client.imap_server:
        return False, "Brak konfiguracji IMAP"

    msg_bytes = msg.as_bytes()
    last_error = ""

    # --- 2. RETRY LOOP (3 próby z exponential backoff) ---
    for attempt in range(1, MAX_IMAP_RETRIES + 1):
        mail = None
        try:
            mail = _imap_connect_and_login(client)

            # Wykryj folder draftów (przy każdej próbie — nowe połączenie)
            selected_folder = _detect_drafts_folder(mail)

            # Append
            typ, dat = mail.append(
                selected_folder,
                '(\\Draft \\Seen)',
                imaplib.Time2Internaldate(time.time()),
                msg_bytes,
            )

            if typ != 'OK':
                raise RuntimeError(
                    f"IMAP APPEND zwrócił '{typ}' dla folderu '{selected_folder}': {dat}"
                )

            # Sukces!
            try:
                mail.logout()
            except Exception:
                pass

            att_info = f"(+ {client.attachment_filename})" if client.attachment_filename else ""
            if attempt > 1:
                logger.info(f"   ✅ [IMAP] Zapisano draft po {attempt} próbie.")
            return True, f"Zapisano w folderze: {selected_folder} {att_info}"

        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"   ⚠️ [IMAP] Próba {attempt}/{MAX_IMAP_RETRIES} nieudana: {last_error}"
            )

            # Sprzątamy połączenie po błędzie
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

            # Backoff przed następną próbą (nie czekaj po ostatniej)
            if attempt < MAX_IMAP_RETRIES:
                wait = IMAP_RETRY_BACKOFF[attempt - 1]
                logger.info(f"   ⏳ [IMAP] Czekam {wait}s przed retryem...")
                time.sleep(wait)

    # Wszystkie próby wyczerpane
    return False, f"IMAP: {MAX_IMAP_RETRIES} prób nieudanych. Ostatni błąd: {last_error}"


def process_followups(session: Session, client: Client, use_queue: bool = False):
    """
    Logika Drip: Przesuwa leady do kolejnego kroku, jeśli minął czas.
    
    NEW: Optional queue integration - if enabled, adds leads to queue
    instead of direct status change.
    
    Args:
        session: DB session
        client: Client object
        use_queue: If True, use Redis queue (for multi-instance deployments)
    """
    # Follow-up delays: step 1→2 = 6 dni, step 2→3 = 7 dni
    # Rozciągnięta sekwencja chroni przed filtrami antyspamowymi
    FOLLOWUP_DELAYS = {
        1: timedelta(days=6),   # Po pierwszym mailu czekaj 6 dni
        2: timedelta(days=7),   # Po drugim mailu czekaj 7 dni
    }

    now = datetime.now(PL_TZ)

    pending_followups = session.query(Lead).join(Lead.campaign).filter(
        Lead.campaign.has(client_id=client.id),
        Lead.status == "SENT",
        Lead.step_number < 3,
        (Lead.replied_at == None)
    ).all()

    if not pending_followups:
        return

    followup_count = 0

    for lead in pending_followups:
        last_action = lead.sent_at or lead.last_action_at
        if not last_action:
            continue

        # Normalizuj do PL_TZ — Railway zwraca naive TIMESTAMP (przechowywany jako UTC)
        if last_action.tzinfo is None:
            last_action = last_action.replace(tzinfo=timezone.utc).astimezone(PL_TZ)

        delay = FOLLOWUP_DELAYS.get(lead.step_number, timedelta(days=7))
        if (now - last_action) < delay:
            continue

        next_step = lead.step_number + 1
        console.print(f"   ⏰ [DRIP] {lead.company.name}: Czas na krok {next_step} (po {delay.days}d).")

        lead.step_number = next_step
        lead.last_action_at = now

        if use_queue and QUEUE_ENABLED:
            queue_manager.push_lead(lead.id, QueueType.ANALYZED)
            logger.info(f"📥 Follow-up lead {lead.id} queued for writing (step {next_step})")
        else:
            lead.status = "ANALYZED"

        followup_count += 1
        session.commit()

    if followup_count > 0:
        logger.info(f"✅ Processed {followup_count} follow-ups for client {client.id}")


def get_followup_stats(session: Session, client: Client) -> dict:
    """
    NEW FUNCTION: Get follow-up statistics for monitoring.
    
    Returns:
        {
            "pending_followups": 12,
            "step_1_sent": 45,
            "step_2_sent": 8,
            "step_3_sent": 2
        }
    """
    from sqlalchemy import func
    
    # Pending follow-ups
    pending = session.query(Lead).join(Lead.campaign).filter(
        Lead.campaign.has(client_id=client.id),
        Lead.status == "SENT",
        Lead.step_number < 3,
        Lead.replied_at == None
    ).count()
    
    # By step number
    steps = {}
    for step in [1, 2, 3]:
        count = session.query(Lead).join(Lead.campaign).filter(
            Lead.campaign.has(client_id=client.id),
            Lead.step_number == step,
            Lead.status == "SENT"
        ).count()
        steps[f"step_{step}_sent"] = count
    
    return {
        "pending_followups": pending,
        **steps
    }
