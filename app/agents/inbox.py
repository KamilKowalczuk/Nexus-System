import imaplib
import email
import os
import re
import ctypes
from email.header import decode_header
from datetime import datetime
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from sqlalchemy.orm import Session
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

from app.database import engine, Lead, Client
from app.schemas import ReplyAnalysis
from app.kms_client import decrypt_credential
from app.rodo_manager import anonymize_lead
from app import stats_manager

load_dotenv()


def _secure_wipe(s: str) -> None:
    """Bezpieczne kasowanie referencji hasła. Samo del wystarczy — GC posprząta."""
    pass


# --- KONFIGURACJA GUARDIANA ---
OPT_OUT_KEYWORDS = [
    "wypisz", "wypisz mnie", "nie chcę", "nie chce",
    "unsubscribe", "stop", "rezygnuję", "rezygnuje",
    "usuń mnie", "usun mnie", "remove me", "opt out", "opt-out",
]

BOUNCE_KEYWORDS = [
    "delivery status notification",
    "delivery failure",
    "undelivered mail returned to sender",
    "mailer-daemon",
    "failure notice",
    "message not delivered",
    "returned mail",
    "adres nie został znaleziony",
    "nie można dostarczyć wiadomości",
    "blocked"
]
# ---------------------------------------

# Model AI do analizy sentymentu
analyst_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0,
    google_api_key=os.getenv("GEMINI_API_KEY")
).with_structured_output(ReplyAnalysis)

def decode_mime_words(s):
    """Pomocnik do dekodowania tematów maili"""
    if not s: return ""
    return u''.join(
        word.decode(encoding or 'utf8') if isinstance(word, bytes) else word
        for word, encoding in decode_header(s)
    )

def get_email_body(msg):
    """Wyciąga czysty tekst z maila"""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))
            if ctype == 'text/plain' and 'attachment' not in cdispo:
                return part.get_payload(decode=True).decode('utf-8', errors='ignore')
    else:
        return msg.get_payload(decode=True).decode('utf-8', errors='ignore')
    return ""

def check_inbox(session: Session, client: Client):
    """Sprawdza skrzynkę odbiorczą w poszukiwaniu odpowiedzi LUB zwrotek."""
    # print(f"📬 INBOX: Sprawdzam pocztę dla {client.name} ({client.smtp_user})...")
    
    if not client.imap_server:
        # print("   ❌ Brak konfiguracji IMAP.")
        return

    try:
        # === POŁĄCZENIE IMAP (143 STARTTLS → 993 SSL) ===
        port = client.imap_port or 993
        mail = None
        _imap_password = decrypt_credential(client.smtp_password or "")

        strategies = [
            ("143+STARTTLS", 143, False),
            ("993+SSL",      993, True),
        ]
        
        connected = False
        try:
            for label, port, use_ssl in strategies:
                try:
                    if use_ssl:
                        mail = imaplib.IMAP4_SSL(client.imap_server, port, timeout=20)
                    else:
                        mail = imaplib.IMAP4(client.imap_server, port, timeout=20)
                    mail.socket().settimeout(30)
                    if not use_ssl and hasattr(mail, 'capabilities') and 'STARTTLS' in mail.capabilities:
                        mail.starttls()
                    mail.login(client.smtp_user, _imap_password)
                    connected = True
                    break
                except Exception:
                    if mail:
                        try: mail.logout()
                        except: pass
                    mail = None
                    continue
            
            if not connected:
                return
        finally:
            del _imap_password

        mail.select("INBOX")

        status, messages = mail.search(None, 'UNSEEN')
        
        email_ids = messages[0].split()
        if not email_ids:
            # print("   📭 Brak nowych wiadomości.") 
            mail.logout() # Ważne: Wyloguj się nawet jak nie ma wiadomości
            return

        print(f"   📨 {client.name}: Znaleziono {len(email_ids)} nowych maili. Analizuję...")

        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Dane nagłówkowe
                    sender_header = decode_mime_words(msg.get("From"))
                    sender_email = email.utils.parseaddr(sender_header)[1]
                    subject = decode_mime_words(msg.get("Subject", "")).lower() 
                    body = get_email_body(msg) 

                    # =================================================================
                    # --- SEKCJA GUARDIAN: WYKRYWANIE BOUNCES ---
                    is_bounce = False
                    if "mailer-daemon" in sender_email.lower() or any(k in subject for k in BOUNCE_KEYWORDS):
                        print(f"   🚨 [BOUNCE] Wykryto zwrotkę: {subject}")
                        is_bounce = True
                        
                        potential_failed_emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', body)
                        
                        found_bounce_lead = False
                        if potential_failed_emails:
                            bounced_lead = session.query(Lead).filter(
                                Lead.target_email.in_(potential_failed_emails)
                            ).first()
                            
                            if bounced_lead:
                                if bounced_lead.status != "BOUNCED":
                                    bounced_lead.status = "BOUNCED"
                                    bounced_lead.ai_analysis_summary = (bounced_lead.ai_analysis_summary or "") + f"\n[SYSTEM]: Mail odrzucony. Powód: {subject}"
                                    print(f"      💀 Oznaczono leada {bounced_lead.company.name} jako BOUNCED.")
                                    session.commit()
                                    # STATS: bounce
                                    try:
                                        cid = bounced_lead.campaign.client_id if bounced_lead.campaign else None
                                        if cid:
                                            stats_manager.increment_bounce(session, cid)
                                    except Exception:
                                        pass
                                found_bounce_lead = True
                        
                        if not found_bounce_lead:
                            print("      ⚠️ Nie udało się powiązać zwrotki z leadem.")
                        
                        continue 
                    # =================================================================

                    # 2. CZY TO NASZ LEAD?
                    lead = session.query(Lead).filter(
                        (Lead.target_email == sender_email) | 
                        (Lead.company.has(domain=sender_email.split('@')[-1]))
                    ).first()

                    if not lead:
                        print(f"   👤 Ignoruję: {sender_email} (Nie ma w bazie leadów)")
                        continue

                    print(f"   🎯 O! Odpisał LEAD ID {lead.id}: {sender_email}")
                    
                    # 3. POBIERZ TREŚĆ 
                    if not body: continue

                    # 4. WYKRYWANIE OPT-OUT (przed analizą AI — wyższy priorytet)
                    body_lower = body.lower()
                    subject_lower = decode_mime_words(msg.get("Subject", "")).lower()
                    is_opt_out = any(
                        kw in body_lower or kw in subject_lower
                        for kw in OPT_OUT_KEYWORDS
                    )

                    if is_opt_out:
                        print(f"   🚫 [OPT-OUT] {lead.company.name} prosi o wypisanie. Anonimizuję...")
                        lead.replied_at = datetime.now(PL_TZ)
                        lead.reply_content = body[:500]
                        lead.reply_sentiment = "NEGATIVE"
                        lead.reply_analysis = "[AUTO OPT-OUT] Wykryto żądanie wypisania."
                        session.commit()
                        # anonymize_lead: hash EMAIL + DOMAIN → opt_outs, usuwa dane osobowe
                        anonymize_lead(session, lead.id)
                        # STATS: opt-out
                        try:
                            cid = lead.campaign.client_id if lead.campaign else None
                            if cid:
                                stats_manager.increment_optout(session, cid)
                        except Exception:
                            pass
                        print(f"   ✅ [OPT-OUT] {lead.company.name}: email + domena na czarnej liście RODO.")
                        continue

                    # 5. ANALIZA AI
                    try:
                        analysis = analyst_llm.invoke(f"Przeanalizuj odpowiedź od klienta:\n\n{body[:2000]}")

                        # 6. AKTUALIZACJA BAZY
                        lead.replied_at = datetime.now(PL_TZ)
                        lead.reply_content = body[:5000]
                        lead.reply_sentiment = analysis.sentiment
                        lead.reply_analysis = f"{analysis.summary} | SUGGESTION: {analysis.suggested_action}"

                        if analysis.is_interested:
                            lead.status = "HOT_LEAD"
                            print(f"   🔥 HOT LEAD! {lead.company.name} jest zainteresowany!")
                        elif analysis.sentiment == "NEGATIVE":
                            lead.status = "NOT_INTERESTED"
                            print(f"   ❄️ Klient nie jest zainteresowany.")
                        else:
                            lead.status = "REPLIED" # Neutralna odpowiedź

                        session.commit()
                        
                        # STATS: reply + response time
                        try:
                            cid = lead.campaign.client_id if lead.campaign else None
                            if cid:
                                sentiment = "POSITIVE" if analysis.is_interested else ("NEGATIVE" if analysis.sentiment == "NEGATIVE" else "NEUTRAL")
                                stats_manager.increment_reply(session, cid, sentiment=sentiment)
                                # Oblicz czas odpowiedzi
                                if lead.sent_at and lead.replied_at:
                                    delta = lead.replied_at - lead.sent_at
                                    hours = round(delta.total_seconds() / 3600, 1)
                                    stats_manager.record_response_time(session, cid, hours)
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"      ❌ Błąd AI podczas analizy inboxa: {e}")

        mail.close()
        mail.logout()

    except TimeoutError:
        print(f"   ⏳ [TIMEOUT] Serwer IMAP klienta {client.name} nie odpowiada (20s). Skip.")
    except Exception as e:
        print(f"   ❌ Błąd IMAP dla {client.name}: {e}")