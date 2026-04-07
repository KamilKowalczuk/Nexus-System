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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from email.message import EmailMessage
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.database import Lead, Client
from app.kms_client import decrypt_credential


def _secure_wipe(s: str) -> None:
    """Best-effort zerowanie stringa w pamięci CPython."""
    if not s:
        return
    try:
        buf_offset = 48  # PyUnicodeObject ASCII compact header on 64-bit
        ctypes.memset(id(s) + buf_offset, 0, len(s))
    except Exception:
        pass
from rich.console import Console

# NEW: Import queue manager (optional integration)
try:
    from app.queue_manager import queue_manager, QueueType
    QUEUE_ENABLED = True
except ImportError:
    QUEUE_ENABLED = False

console = Console()
logger = logging.getLogger("scheduler")

def save_draft_via_imap(lead: Lead, client: Client):
    """
    Zapisuje draft z załącznikiem (PDF/DOCX) na serwerze IMAP.
    Używane przez main.py.
    
    NO CHANGES - This function works perfectly as-is.
    """
    msg = EmailMessage()
    msg["Subject"] = lead.generated_email_subject
    msg["From"] = f"{client.sender_name} <{client.smtp_user}>"
    
    if lead.target_email:
        msg["To"] = lead.target_email
    else:
        return False, "Brak adresu email."
    
    # --- TREŚĆ MAILA (kompletna — writer.py już zmontował body + podpis + stopkę + RODO) ---
    final_html_body = lead.generated_email_body
    
    # Wersja tekstowa - generowana z HTML (Bezpieczeństwo filtry SPAM)
    soup = BeautifulSoup(final_html_body, "html.parser")
    text_content = soup.get_text(separator="\n", strip=True)
    msg.set_content(text_content)
    
    # Wersja HTML (główna)
    msg.add_alternative(final_html_body, subtype="html")

    # --- OBSŁUGA ZAŁĄCZNIKA ---
    if client.attachment_filename:
        # Szukamy w folderze files/ o poziom wyżej od app/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, 'files', client.attachment_filename)
        
        if os.path.exists(file_path):
            ctype, encoding = mimetypes.guess_type(file_path)
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'
            
            maintype, subtype = ctype.split('/', 1)

            with open(file_path, 'rb') as f:
                file_data = f.read()
                msg.add_attachment(
                    file_data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=client.attachment_filename
                )
        else:
            console.print(f"[bold red]⚠️ BŁĄD ZAŁĄCZNIKA:[/bold red] Nie znaleziono pliku '{client.attachment_filename}'")
    # -------------------------------

    try:
        if not client.imap_server: return False, "Brak konfiguracji IMAP"

        # KMS: deszyfrowanie hasła tuż przed connect(), secure wipe po użyciu
        _imap_password = decrypt_credential(client.smtp_password or "")

        # Łączenie z IMAP
        mail = imaplib.IMAP4_SSL(client.imap_server, client.imap_port or 993)
        try:
            mail.login(client.smtp_user, _imap_password)
        finally:
            _secure_wipe(_imap_password)
            del _imap_password
        
        # Wybór folderu Drafts
        selected_folder = "Drafts"
        folders_to_try = ["[Gmail]/Drafts", "Drafts", "Draft", "Wersje robocze", "INBOX.Drafts"]
        try:
            status, folder_list_raw = mail.list()
            f_list = str(folder_list_raw)
            for f in folders_to_try:
                if f in f_list or f.replace("/", "&") in f_list: 
                    selected_folder = f
                    break
        except: pass

        # Zapis draftu
        mail.append(selected_folder, '(\\Draft \\Seen)', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        mail.logout()
        
        att_info = f"(+ {client.attachment_filename})" if client.attachment_filename else ""
        return True, f"Zapisano w folderze: {selected_folder} {att_info}"
    except Exception as e:
        return False, str(e)


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
