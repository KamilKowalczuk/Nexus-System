"""
import_rpwdl.py — Jednorazowy skrypt importu podmiotów medycznych z RPWDL do Nexus Engine.

Buckets:
    A (Gold):       Email + WWW       → GlobalCompany + Lead
    B (Researcher): WWW bez Email     → GlobalCompany (researcher znajdzie mail)
    C (Email Only): Email bez WWW     → GlobalCompany + Lead (domena = @email)
    D (Phone Only): Telefon (bez E/W) → GlobalCompany (source=MEDIC_PHONE)
    E (Discard):    Brak kontaktu     → pominięty

TERYT prefix 06 = województwo lubelskie → Lead dla klienta "Koordynuj Zdrowie".
Reszta → Lead dla klienta "GLOBAL_MEDICAL_POOL" (tworzony automatycznie jeśli nie istnieje).

Usage:
    python import_rpwdl.py                    # DRY-RUN (tylko statystyki)
    python import_rpwdl.py --commit           # Zapis do bazy
    python import_rpwdl.py --commit --verbose # Zapis + logi per-rekord
"""

import csv
import sys
import argparse
import logging
from urllib.parse import urlparse
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CSV_PATH = "context/podmioty.csv"
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8"

TERYT_LUBELSKIE_PREFIX = "06"
CLIENT_NAME_LUBELSKIE = "Koordynuj Zdrowie"
CLIENT_NAME_GLOBAL = "GLOBAL_MEDICAL_POOL"
CAMPAIGN_NAME_LUBELSKIE = "RPWDL — Placówki Lubelskie"
CAMPAIGN_NAME_GLOBAL = "RPWDL — Pula Ogólnopolska"

SOURCE_TAG = "RPWDL"
SOURCE_TAG_PHONE = "MEDIC_PHONE"

PL_TZ = ZoneInfo("Europe/Warsaw")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rpwdl_import")


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _clean_null(value: str) -> Optional[str]:
    """Zamienia stringi 'NULL' i puste na None."""
    if not value or value.strip().upper() == "NULL":
        return None
    return value.strip()


def _extract_domain(url: str) -> Optional[str]:
    """Wyciąga czystą domenę z URL (bez http/www)."""
    url = url.strip()
    if not url:
        return None
    # Dodaj scheme jeśli brak
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.hostname
        if domain:
            # Usuń www.
            domain = domain.lower().removeprefix("www.")
            # Odrzuć śmieci (np. puste, za krótkie)
            if "." in domain and len(domain) > 3:
                return domain
    except Exception:
        pass
    return None


def _domain_from_email(email: str) -> Optional[str]:
    """Wyciąga domenę z adresu email (po @)."""
    email = email.strip().lower()
    if "@" in email:
        domain = email.split("@", 1)[1]
        if "." in domain and len(domain) > 3:
            return domain
    return None


def _build_address(row: dict) -> Optional[str]:
    """Składa adres z pól CSV."""
    parts: list[str] = []
    ulica = _clean_null(row.get("Ulica", ""))
    budynek = _clean_null(row.get("Budynek", ""))
    lokal = _clean_null(row.get("Lokal", ""))
    kod = _clean_null(row.get("Kod pocztowy", ""))
    miasto = _clean_null(row.get("Miejscowość", ""))

    if ulica:
        street = ulica
        if budynek:
            street += f" {budynek}"
        if lokal:
            street += f"/{lokal}"
        parts.append(street)
    elif budynek:
        parts.append(budynek)

    if kod and miasto:
        parts.append(f"{kod} {miasto}")
    elif miasto:
        parts.append(miasto)

    return ", ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# CLASSIFICATOR (Bucket Engine)
# ---------------------------------------------------------------------------

def classify_row(row: dict) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Klasyfikuje rekord CSV do odpowiedniego koszyka.

    Returns:
        (bucket, domain, email, phone)
        bucket: 'A' | 'B' | 'C' | 'D' | 'E'
    """
    email = _clean_null(row.get("Email", ""))
    www = _clean_null(row.get("Strona WWW", ""))
    phone = _clean_null(row.get("Telefon", ""))

    domain_from_www = _extract_domain(www) if www else None
    domain_from_mail = _domain_from_email(email) if email else None

    has_email = email is not None
    has_www = domain_from_www is not None
    has_phone = phone is not None

    if has_email and has_www:
        return ("A", domain_from_www, email, phone)
    elif has_www and not has_email:
        return ("B", domain_from_www, None, phone)
    elif has_email and not has_www:
        return ("C", domain_from_mail, email, phone)
    elif has_phone:
        return ("D", None, None, phone)
    else:
        return ("E", None, None, None)


# ---------------------------------------------------------------------------
# MAIN IMPORT LOGIC
# ---------------------------------------------------------------------------

def run_import(commit: bool = False, verbose: bool = False) -> None:
    """Główna procedura importu RPWDL."""

    # --- STATS ---
    stats = {
        "total": 0,
        "skipped_inactive": 0,
        "bucket_A": 0, "bucket_B": 0, "bucket_C": 0,
        "bucket_D": 0, "bucket_E": 0,
        "lubelskie_leads": 0,
        "global_leads": 0,
        "companies_created": 0,
        "companies_existing": 0,
        "leads_created": 0,
        "leads_duplicate": 0,
    }

    # --- Wczytaj CSV ---
    logger.info(f"📂 Wczytuję plik: {CSV_PATH}")
    with open(CSV_PATH, "r", encoding=CSV_ENCODING) as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER, quotechar='"')
        rows = list(reader)
    stats["total"] = len(rows)
    logger.info(f"📊 Wczytano {stats['total']} rekordów")

    if not commit:
        logger.info("🏃 TRYB DRY-RUN — żadne dane nie zostaną zapisane do bazy")

    # --- Sesja DB (lazy import — dry-run nie wymaga połączenia z bazą) ---
    session = None
    if commit:
        from sqlalchemy import text
        from app.database import SessionLocal, GlobalCompany, Lead, Client, Campaign
        session = SessionLocal()

    try:
        # --- Pobranie/Tworzenie klientów i kampanii ---
        client_lubelskie: Optional[Client] = None
        client_global: Optional[Client] = None
        campaign_lubelskie: Optional[Campaign] = None
        campaign_global: Optional[Campaign] = None

        if commit:
            # Klient lubelski MUSI istnieć
            client_lubelskie = session.query(Client).filter(Client.name == CLIENT_NAME_LUBELSKIE).first()
            if not client_lubelskie:
                logger.error(f"❌ Klient '{CLIENT_NAME_LUBELSKIE}' NIE ISTNIEJE w bazie! "
                             f"Utwórz go ręcznie w NocoDB przed importem.")
                sys.exit(1)
            logger.info(f"✅ Klient lubelski: {client_lubelskie.name} (id={client_lubelskie.id})")

            # Klient globalny — tworzony automatycznie jeśli nie istnieje
            client_global = session.query(Client).filter(Client.name == CLIENT_NAME_GLOBAL).first()
            if not client_global:
                client_global = Client(
                    name=CLIENT_NAME_GLOBAL,
                    status="PAUSED",
                    mode="SALES",
                    industry="Medical (Multi-Region Pool)",
                    value_proposition="Pula placówek medycznych z RPWDL do przyszłych kampanii",
                    daily_limit=0,  # Nie wysyłaj nic — to magazyn
                    sending_mode="DRAFT",
                )
                session.add(client_global)
                session.flush()
                logger.info(f"🆕 Utworzono klienta globalnego: {client_global.name} (id={client_global.id})")
            else:
                logger.info(f"✅ Klient globalny: {client_global.name} (id={client_global.id})")

            # Kampanie
            campaign_lubelskie = session.query(Campaign).filter(
                Campaign.client_id == client_lubelskie.id,
                Campaign.name == CAMPAIGN_NAME_LUBELSKIE
            ).first()
            if not campaign_lubelskie:
                campaign_lubelskie = Campaign(
                    client_id=client_lubelskie.id,
                    name=CAMPAIGN_NAME_LUBELSKIE,
                    status="ACTIVE",
                    strategy_prompt="Import z rejestru RPWDL — placówki medyczne woj. lubelskie",
                    target_region="lubelskie",
                )
                session.add(campaign_lubelskie)
                session.flush()
                logger.info(f"🆕 Kampania lubelska: id={campaign_lubelskie.id}")

            campaign_global = session.query(Campaign).filter(
                Campaign.client_id == client_global.id,
                Campaign.name == CAMPAIGN_NAME_GLOBAL
            ).first()
            if not campaign_global:
                campaign_global = Campaign(
                    client_id=client_global.id,
                    name=CAMPAIGN_NAME_GLOBAL,
                    status="PAUSED",
                    strategy_prompt="Import z rejestru RPWDL — placówki medyczne cała Polska (pula do przyszłych kampanii)",
                    target_region="Polska",
                )
                session.add(campaign_global)
                session.flush()
                logger.info(f"🆕 Kampania globalna: id={campaign_global.id}")

            # Preload istniejących domen do setu (O(1) lookup zamiast query per rekord)
            existing_domains: set[str] = set()
            domain_rows = session.execute(text("SELECT domain FROM global_companies")).fetchall()
            for (d,) in domain_rows:
                if d:
                    existing_domains.add(d.lower())
            logger.info(f"📦 Załadowano {len(existing_domains)} istniejących domen z bazy")

            # Pamięć na nowo tworzone leady w tym przebiegu (chroni przed duplikatami w paczce przed flushem)
            session_created_leads: set[tuple[int, int]] = set()

        # --- Przetwarzanie rekordów ---
        for i, row in enumerate(rows):
            # Filtracja nieaktywnych
            data_wykreslenia = _clean_null(row.get("Data wykreślenia z rejestru", ""))
            if data_wykreslenia is not None:
                stats["skipped_inactive"] += 1
                continue

            # Klasyfikacja
            bucket, domain, email, phone = classify_row(row)
            stats[f"bucket_{bucket}"] += 1

            if bucket == "E":
                continue  # Brak kontaktu — pomijamy

            # Identyfikator TERYT
            teryt = _clean_null(row.get("Teryt", ""))
            is_lubelskie = teryt is not None and teryt.startswith(TERYT_LUBELSKIE_PREFIX)

            # Nazwa podmiotu
            nazwa = _clean_null(row.get("Nazwa", "")) or _clean_null(row.get("Nazwa podmiotu", "")) or "Podmiot RPWDL"
            id_ksiegi = _clean_null(row.get("ID Księgi", ""))
            nip = _clean_null(row.get("NIP", ""))

            # Adres fizyczny
            address = _build_address(row)

            # Forma organizacyjno-prawna
            forma = _clean_null(row.get("Forma organizacyjno-prawna opis", ""))

            # Ustal źródło
            source_tag = SOURCE_TAG_PHONE if bucket == "D" else SOURCE_TAG

            # --- Domena: syntetyczny klucz dla Bucket D ---
            if bucket == "D" and domain is None:
                # Generuj syntetyczny identyfikator
                domain = f"rpwdl-phone-{id_ksiegi}.no-domain" if id_ksiegi else f"rpwdl-phone-{i}.no-domain"

            if domain is None:
                # Fallback — nie powinno się zdarzyć, ale safety net
                stats["bucket_E"] += 1
                stats[f"bucket_{bucket}"] -= 1
                continue

            if verbose:
                logger.info(f"  [{bucket}] {nazwa[:50]} | {domain} | teryt={teryt} | {'🟢 LUB' if is_lubelskie else '⚪ REST'}")

            # --- Zliczanie leadów per region (dry-run + commit) ---
            if bucket in ("A", "C"):
                if is_lubelskie:
                    stats["lubelskie_leads"] += 1
                else:
                    stats["global_leads"] += 1

            # --- ZAPIS DO BAZY ---
            if commit:
                domain_lower = domain.lower()

                # Sprawdź duplikat domeny
                if domain_lower in existing_domains:
                    stats["companies_existing"] += 1

                    # Pobierz istniejącą firmę aby dodać lead
                    company = session.query(GlobalCompany).filter(
                        GlobalCompany.domain == domain_lower
                    ).first()

                    if company:
                        # Aktualizuj teryt_code i source jeśli puste
                        if not company.teryt_code and teryt:
                            company.teryt_code = teryt
                        if not company.source:
                            company.source = source_tag
                        # Aktualizuj telefon jeśli pusty
                        if not company.phone_number and phone:
                            company.phone_number = phone
                else:
                    # Nowa firma
                    company = GlobalCompany(
                        domain=domain_lower,
                        name=nazwa,
                        industry=forma,
                        address=address,
                        phone_number=phone,
                        teryt_code=teryt,
                        source=source_tag,
                        is_active=True,
                        quality_score=0,
                    )
                    session.add(company)
                    session.flush() # Natychmiast ustala company.id
                    existing_domains.add(domain_lower)
                    stats["companies_created"] += 1

                # --- Tworzenie Lead'a (tylko Bucket A i C) ---
                if company and company.id and bucket in ("A", "C"):
                    if is_lubelskie:
                        target_client = client_lubelskie
                        target_campaign = campaign_lubelskie
                    else:
                        target_client = client_global
                        target_campaign = campaign_global

                    # Klucz deduplikacyjny na ten cykl importu
                    lead_key = (target_client.id, company.id)

                    # Sprawdź duplikat leada (Baza danych LUB Pamięć podręczna tego skryptu)
                    if lead_key in session_created_leads:
                        existing_lead = True
                    else:
                        existing_lead = session.query(Lead).filter(
                            Lead.client_id == target_client.id,
                            Lead.global_company_id == company.id,
                        ).first()

                    if existing_lead:
                        stats["leads_duplicate"] += 1
                    else:
                        lead = Lead(
                            campaign_id=target_campaign.id,
                            client_id=target_client.id,
                            global_company_id=company.id,
                            target_email=email,
                            status="NEW",
                            step_number=1,
                            ai_confidence_score=0,
                            last_action_at=datetime.now(PL_TZ),
                        )
                        session.add(lead)
                        session_created_leads.add(lead_key)
                        stats["leads_created"] += 1

            # Flush co 500 rekordów (zmniejszy zużycie RAM)
            if commit and i > 0 and i % 500 == 0:
                session.flush()
                logger.info(f"   ⏳ Przetworzono {i}/{stats['total']}...")

        # --- COMMIT ---
        if commit:
            session.commit()
            logger.info("💾 Dane zapisane do bazy (COMMIT)")
        else:
            logger.info("🏃 DRY-RUN zakończony — baza NIE została zmodyfikowana")

    except Exception as e:
        if commit:
            session.rollback()
        logger.error(f"💥 Błąd importu: {e}", exc_info=True)
        raise
    finally:
        if session:
            session.close()

    # --- RAPORT ---
    print("\n" + "=" * 65)
    print("  📋 RAPORT IMPORTU RPWDL")
    print("=" * 65)
    print(f"  Łączna liczba rekordów w pliku:     {stats['total']:>7}")
    print(f"  Pominięte (wykreślone z rejestru):  {stats['skipped_inactive']:>7}")
    print(f"  ─────────────────────────────────────────")
    print(f"  🥇 Bucket A (Email + WWW):          {stats['bucket_A']:>7}")
    print(f"  🔍 Bucket B (WWW, brak Email):      {stats['bucket_B']:>7}")
    print(f"  📧 Bucket C (Email, brak WWW):      {stats['bucket_C']:>7}")
    print(f"  📞 Bucket D (Tylko telefon):        {stats['bucket_D']:>7}")
    print(f"  🗑️  Bucket E (Brak kontaktu):        {stats['bucket_E']:>7}")
    print(f"  ─────────────────────────────────────────")
    print(f"  📬 Potencjalne leady (A+C):         {stats['lubelskie_leads'] + stats['global_leads']:>7}")
    print(f"     ├─ 🟢 Lubelskie (Koordynuj):     {stats['lubelskie_leads']:>7}")
    print(f"     └─ ⚪ Reszta (Global Pool):      {stats['global_leads']:>7}")
    if commit:
        print(f"  ─────────────────────────────────────────")
        print(f"  🏢 Firmy utworzone (nowe):           {stats['companies_created']:>7}")
        print(f"  🏢 Firmy istniejące (aktualizacja):  {stats['companies_existing']:>7}")
        print(f"  📬 Leady zapisane:                  {stats['leads_created']:>7}")
        print(f"  ⚠️  Leady-duplikaty (pominięte):     {stats['leads_duplicate']:>7}")
    print("=" * 65)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import podmiotów medycznych z RPWDL do Nexus Engine")
    parser.add_argument("--commit", action="store_true", help="Zapisz dane do bazy (bez tego flaga = dry-run)")
    parser.add_argument("--verbose", action="store_true", help="Loguj każdy przetwarzany rekord")
    args = parser.parse_args()

    run_import(commit=args.commit, verbose=args.verbose)
