"""
🚨 SKRYPT RATUNKOWY: Odzyskiwanie wysłanych leadów z folderu WYSŁANE (IMAP)
=============================================================================
Łączy się z IMAP klienta, czyta "Sent"/"Wysłane", wyciąga adresy odbiorców
i wstawia je do bazy jako leady ze statusem SENT — dzięki temu bot NIE wyśle
do nich ponownie.
"""

import os
import imaplib
import email as email_mod
from email.header import decode_header
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()

from app.database import engine, SessionLocal, Lead, Campaign, Client, GlobalCompany
from app.kms_client import decrypt_credential

PL_TZ = ZoneInfo("Europe/Warsaw")

# Foldery Sent do sprawdzenia (różne serwery nazywają inaczej)
SENT_FOLDERS = [
    "Sent", "INBOX.Sent", "Sent Messages", "Sent Items",
    "[Gmail]/Sent Mail", "[Gmail]/Wysłane",
    "Wysłane", "INBOX.Wysłane",
]


def decode_mime(s):
    if not s:
        return ""
    return "".join(
        word.decode(enc or "utf8") if isinstance(word, bytes) else word
        for word, enc in decode_header(s)
    )


def find_sent_folder(mail):
    """Próbuje znaleźć folder Sent na serwerze IMAP."""
    # Listuj wszystkie foldery
    status, folders = mail.list()
    if status != "OK":
        return None
    
    available = []
    for f in folders:
        try:
            name = f.decode().split('"')[-2] if b'"' in f else f.decode().split()[-1]
            available.append(name)
        except:
            pass
    
    print(f"   📂 Dostępne foldery IMAP: {available}")
    
    for candidate in SENT_FOLDERS:
        if candidate in available:
            return candidate
    
    # Próba fuzzy match
    for folder in available:
        if "sent" in folder.lower() or "wysł" in folder.lower():
            return folder
    
    return None


def recover_for_client(session: Session, client: Client):
    """Odzyskuje leady z folderu Wysłane dla jednego klienta."""
    print(f"\n{'='*60}")
    print(f"🔍 ODZYSKIWANIE: {client.name} ({client.smtp_user})")
    print(f"{'='*60}")

    if not client.imap_server or not client.smtp_user:
        print("   ❌ Brak IMAP config. Skip.")
        return 0

    # Znajdź kampanię tego klienta
    campaign = session.query(Campaign).filter(
        Campaign.client_id == client.id,
        Campaign.status == "ACTIVE"
    ).first()
    
    if not campaign:
        campaign = session.query(Campaign).filter(
            Campaign.client_id == client.id
        ).first()
    
    if not campaign:
        print("   ❌ Brak kampanii dla klienta. Skip.")
        return 0

    # Połącz z IMAP
    _password = decrypt_credential(client.smtp_password or "")
    mail = None
    try:
        strategies = [
            (143, False),
            (993, True),
        ]
        
        for port, use_ssl in strategies:
            try:
                if use_ssl:
                    mail = imaplib.IMAP4_SSL(client.imap_server, port, timeout=30)
                else:
                    mail = imaplib.IMAP4(client.imap_server, port, timeout=30)
                    if hasattr(mail, 'capabilities') and 'STARTTLS' in mail.capabilities:
                        mail.starttls()
                mail.login(client.smtp_user, _password)
                print(f"   ✅ Połączono z IMAP ({client.imap_server}:{port})")
                break
            except Exception as e:
                if mail:
                    try: mail.logout()
                    except: pass
                mail = None
                continue
    finally:
        del _password

    if not mail:
        print("   ❌ Nie udało się połączyć z IMAP.")
        return 0

    # Znajdź folder Sent
    sent_folder = find_sent_folder(mail)
    if not sent_folder:
        print("   ❌ Nie znaleziono folderu Sent/Wysłane.")
        mail.logout()
        return 0

    print(f"   📨 Otwieram folder: {sent_folder}")
    status, _ = mail.select(sent_folder, readonly=True)
    if status != "OK":
        print(f"   ❌ Nie mogę otworzyć folderu {sent_folder}")
        mail.logout()
        return 0

    # Pobierz WSZYSTKIE maile z folderu Sent
    status, messages = mail.search(None, "ALL")
    if status != "OK":
        mail.logout()
        return 0

    email_ids = messages[0].split()
    print(f"   📊 Znaleziono {len(email_ids)} maili w folderze Sent")

    recovered = 0
    skipped = 0
    
    # Zbieramy obecne adresy w bazie żeby nie duplikować
    existing_emails = set()
    existing_leads = session.query(Lead.target_email).filter(
        Lead.campaign_id == campaign.id,
        Lead.target_email != None
    ).all()
    existing_emails = {e[0].lower() for e in existing_leads if e[0]}

    for e_id in email_ids:
        try:
            # Pobierz TYLKO nagłówki (szybciej)
            _, msg_data = mail.fetch(e_id, "(RFC822.HEADER)")
            if not msg_data or not msg_data[0]:
                continue
            
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email_mod.message_from_bytes(raw)

            # Kto jest odbiorcą?
            to_header = decode_mime(msg.get("To", ""))
            if not to_header:
                continue
            
            # Wyciągnij email
            _, to_email = email_mod.utils.parseaddr(to_header)
            if not to_email or "@" not in to_email:
                continue
            
            to_email = to_email.lower().strip()
            
            # Pomiń własne adresy i systemowe
            if to_email == client.smtp_user.lower():
                continue
            if any(x in to_email for x in ["mailer-daemon", "postmaster", "noreply", "no-reply"]):
                continue

            # Już istnieje?
            if to_email in existing_emails:
                skipped += 1
                continue

            # Wyciągnij datę
            date_str = msg.get("Date", "")
            sent_at = None
            try:
                from email.utils import parsedate_to_datetime
                sent_at = parsedate_to_datetime(date_str)
            except:
                sent_at = datetime.now(PL_TZ)

            # Wyciągnij subject
            subject = decode_mime(msg.get("Subject", ""))

            # Wyciągnij domenę
            domain = to_email.split("@")[1] if "@" in to_email else ""

            # Znajdź lub stwórz GlobalCompany
            company = session.query(GlobalCompany).filter(
                GlobalCompany.domain == domain
            ).first()
            
            if not company:
                company = GlobalCompany(
                    domain=domain,
                    name=domain.split(".")[0].capitalize(),
                    first_seen_at=sent_at or datetime.now(PL_TZ)
                )
                session.add(company)
                session.flush()

            # Stwórz Lead jako SENT
            lead = Lead(
                campaign_id=campaign.id,
                global_company_id=company.id,
                target_email=to_email,
                generated_email_subject=subject or "[Recovered]",
                generated_email_body="[Odzyskano z folderu Wysłane]",
                status="SENT",
                step_number=1,
                sent_at=sent_at,
                ai_confidence_score=0.0,
                ai_analysis_summary="[RECOVERED] Lead odzyskany z IMAP Sent folder",
            )
            session.add(lead)
            existing_emails.add(to_email)
            recovered += 1

            print(f"   ✅ Odzyskano: {to_email} ({domain}) → SENT")

        except Exception as e:
            print(f"   ⚠️ Błąd przetwarzania e_id {e_id}: {e}")
            continue

    session.commit()
    mail.close()
    mail.logout()

    print(f"\n   📊 PODSUMOWANIE {client.name}:")
    print(f"      ✅ Odzyskano: {recovered} leadów")
    print(f"      ⏩ Pominięto (już w bazie): {skipped}")
    
    return recovered


def main():
    print("=" * 60)
    print("🚨 NEXUS RECOVERY TOOL — Odzyskiwanie leadów z IMAP")
    print("=" * 60)

    with SessionLocal() as session:
        clients = session.query(Client).all()
        
        if not clients:
            print("❌ Brak klientów w bazie!")
            return
        
        total = 0
        for client in clients:
            total += recover_for_client(session, client)

        print(f"\n{'='*60}")
        print(f"🏁 KONIEC. Łącznie odzyskano: {total} leadów")
        print(f"   Bot NIE wyśle do tych adresów ponownie.")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
