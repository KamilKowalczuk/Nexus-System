#!/usr/bin/env python3
"""
Skrypt do ustawiania czytelnych nazw kolumn w NocoDB.
Używa NocoDB API v2 do zmiany wyświetlanych tytułów (display titles).
Kolumny techniczne w bazie (np. 'ai_analysis_summary') → czytelne nazwy (np. 'Analiza AI').
"""

import requests
import sys
import json
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# KONFIGURACJA — uzupełnij URL do NocoDB
# ============================================================
NOCODB_URL = os.getenv("NOCODB_URL")
NOCODB_TOKEN = os.getenv("NOCODB_TOKEN")

if not NOCODB_URL or not NOCODB_TOKEN:
    print("❌ Brak NOCODB_URL lub NOCODB_TOKEN w .env")
    sys.exit(1)

HEADERS = {
    "xc-token": NOCODB_TOKEN,
    "Content-Type": "application/json",
}

# ============================================================
# MAPA NAZW: kolumna_techniczna → nazwa_wyświetlana_pl
# ============================================================
COLUMN_RENAMES = {
    # ===================== TABELA: leads =====================
    "leads": {
        "id": "ID",
        "campaign_id": "Nr kampanii",
        "client_id": "Nr klienta",
        "global_company_id": "Nr firmy (global)",
        "ai_analysis_summary": "📋 Analiza Researchera",
        "generated_email_subject": "📧 Temat maila",
        "generated_email_body": "📧 Treść maila",
        "target_email": "📬 Email docelowy",
        "ai_confidence_score": "🎯 Pewność AI (0-100)",
        "status": "📌 Status",
        "step_number": "🔄 Numer kroku (FUP)",
        "last_action_at": "🕐 Ostatnia akcja",
        "scheduled_for": "📅 Zaplanowany na",
        "sent_at": "📤 Wysłano",
        "replied_at": "💬 Odpowiedź — kiedy",
        "reply_content": "💬 Treść odpowiedzi",
        "reply_sentiment": "💬 Sentyment odpowiedzi",
        "reply_analysis": "💬 Analiza odpowiedzi (AI)",
    },

    # ===================== TABELA: lead_feedback =====================
    "lead_feedback": {
        "id": "ID",
        "lead_id": "Nr leada",
        "researcher_rating": "⭐ Ocena Researchera (1-5)",
        "writer_rating": "⭐ Ocena Writera (1-5)",
        "researcher_comments": "💬 Komentarz — Research",
        "writer_comments": "💬 Komentarz — Writer",
        "corrected_subject": "✏️ Poprawiony temat",
        "corrected_body": "✏️ Poprawiona treść",
        "is_processed": "🤖 Przetworzone przez Teachera",
        "created_at": "📅 Utworzono",
        "updated_at": "📅 Zaktualizowano",
    },

    # ===================== TABELA: client_alignments =====================
    "client_alignments": {
        "client_id": "Nr klienta",
        "strategy_guidelines": "📝 Reguły Strategii",
        "scouting_guidelines": "📝 Reguły Scouta",
        "research_guidelines": "📝 Reguły Researchera",
        "writing_guidelines": "📝 Reguły Writera",
        "gold_examples": "🏆 Złote/Czarne przykłady (JSON)",
        "version": "🔢 Wersja",
        "avg_rating_at_synthesis": "📊 Śr. ocena przy syntezie",
        "feedbacks_processed_count": "📊 Liczba przetworzonych ocen",
        "last_updated": "📅 Ostatnia aktualizacja",
    },

    # ===================== TABELA: alignment_history =====================
    "alignment_history": {
        "id": "ID",
        "client_id": "Nr klienta",
        "version": "🔢 Wersja (archiwalna)",
        "strategy_guidelines": "📝 Reguły Strategii",
        "scouting_guidelines": "📝 Reguły Scouta",
        "research_guidelines": "📝 Reguły Researchera",
        "writing_guidelines": "📝 Reguły Writera",
        "gold_examples": "🏆 Złote/Czarne przykłady (JSON)",
        "avg_rating_at_synthesis": "📊 Śr. ocena",
        "archived_at": "📅 Zarchiwizowano",
    },

    # ===================== TABELA: clients =====================
    "clients": {
        "id": "ID",
        "status": "📌 Status",
        "mode": "🎯 Tryb (SALES/JOB_HUNT)",
        "name": "🏢 Nazwa marki",
        "nip": "NIP",
        "legal_name": "Pełna nazwa prawna (KRS)",
        "payload_order_id": "Payload: nr zamówienia",
        "payload_brief_id": "Payload: nr briefu",
        "industry": "🏭 Branża",
        "value_proposition": "💡 Propozycja wartości",
        "ideal_customer_profile": "🎯 Profil idealnego klienta (ICP)",
        "tone_of_voice": "🗣 Ton komunikacji",
        "negative_constraints": "🚫 Zakazy / ograniczenia",
        "case_studies": "📚 Case studies",
        "sender_name": "📧 Imię nadawcy",
        "smtp_user": "📧 Adres email nadawcy",
        "smtp_password": "🔐 Hasło SMTP (zaszyfrowane)",
        "smtp_server": "⚙️ Serwer SMTP",
        "smtp_port": "⚙️ Port SMTP",
        "imap_server": "⚙️ Serwer IMAP",
        "imap_port": "⚙️ Port IMAP",
        "daily_limit": "📊 Dzienny limit wysyłki",
        "html_footer": "📄 Stopka HTML",
        "warmup_enabled": "🔥 Warm-up włączony?",
        "warmup_start_limit": "🔥 Warm-up: start od",
        "warmup_increment": "🔥 Warm-up: przyrost/dzień",
        "warmup_started_at": "🔥 Warm-up: data startu",
        "sending_mode": "📤 Tryb wysyłki (DRAFT/SEND)",
        "privacy_policy_url": "🔒 URL polityki prywatności",
        "opt_out_link": "🔒 URL wypisania (opt-out)",
        "scout_model": "🤖 Model AI: Scout",
        "researcher_model": "🤖 Model AI: Researcher",
        "writer_model": "🤖 Model AI: Writer",
        "teacher_model": "🤖 Model AI: Teacher",
        "gatekeeper_strictness": "🤖 Rygor Gatekeepera",
    },

    # ===================== TABELA: campaigns =====================
    "campaigns": {
        "id": "ID",
        "client_id": "Nr klienta",
        "name": "📛 Nazwa kampanii",
        "status": "📌 Status",
        "strategy_prompt": "🎯 Prompt strategii",
        "target_region": "🌍 Region docelowy",
    },

    # ===================== TABELA: global_companies =====================
    "global_companies": {
        "id": "ID",
        "domain": "🌐 Domena",
        "name": "🏢 Nazwa firmy",
        "industry": "🏭 Branża (Google Maps)",
        "address": "📍 Adres",
        "phone_number": "📞 Telefon",
        "tech_stack": "💻 Tech stack (JSON)",
        "decision_makers": "👔 Decydenci (JSON)",
        "pain_points": "⚡ Pain points (JSON)",
        "hiring_status": "👥 Status rekrutacji",
        "is_active": "✅ Aktywna?",
        "has_mx_records": "📧 Ma rekordy MX?",
        "last_scraped_at": "🕐 Ostatnie skanowanie",
        "quality_score": "🎯 Wynik jakości (0-100)",
    },
}


def get_tables():
    """Pobiera listę tabel z NocoDB."""
    # Najpierw pobierz listę baz (sources)
    resp = requests.get(f"{NOCODB_URL}/api/v2/meta/bases/", headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ Błąd pobierania baz: {resp.status_code} {resp.text}")
        return None
    bases = resp.json().get("list", [])
    if not bases:
        print("❌ Brak baz danych w NocoDB")
        return None
    
    base_id = bases[0]["id"]
    print(f"📦 Znaleziono bazę: {bases[0].get('title', base_id)}")
    
    resp = requests.get(f"{NOCODB_URL}/api/v2/meta/tables/?baseId={base_id}", headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ Błąd pobierania tabel: {resp.status_code} {resp.text}")
        return None
    return resp.json().get("list", [])


def get_columns(table_id):
    """Pobiera kolumny tabeli."""
    resp = requests.get(f"{NOCODB_URL}/api/v2/meta/tables/{table_id}", headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ Błąd pobierania kolumn: {resp.status_code}")
        return []
    return resp.json().get("columns", [])


def rename_column(column_id, column_name, new_title):
    """Zmienia wyświetlaną nazwę kolumny."""
    payload = {
        "title": new_title,
        "column_name": column_name,
    }
    resp = requests.patch(
        f"{NOCODB_URL}/api/v2/meta/columns/{column_id}",
        headers=HEADERS,
        json=payload,
    )
    if resp.status_code == 200:
        return True
    else:
        print(f"   ⚠️ Błąd rename {column_name} → {new_title}: {resp.status_code} {resp.text[:100]}")
        return False


def main():
    if NOCODB_URL == "UZUPELNIJ_URL":
        print("❌ Uzupełnij NOCODB_URL w skrypcie!")
        sys.exit(1)

    print(f"🔗 Łączę z NocoDB: {NOCODB_URL}")
    tables = get_tables()
    if not tables:
        sys.exit(1)

    print(f"📋 Znaleziono {len(tables)} tabel\n")
    
    total_renamed = 0
    for table in tables:
        table_name = table.get("table_name", "")
        table_title = table.get("title", table_name)
        table_id = table["id"]
        
        if table_name not in COLUMN_RENAMES:
            continue
        
        renames = COLUMN_RENAMES[table_name]
        columns = get_columns(table_id)
        
        if not columns:
            continue
        
        print(f"📄 Tabela: {table_name} ({len(columns)} kolumn)")
        renamed = 0
        
        for col in columns:
            col_name = col.get("column_name", "")
            col_id = col.get("id")
            current_title = col.get("title", col_name)
            
            if col_name in renames:
                new_title = renames[col_name]
                if current_title == new_title:
                    continue  # Już ustawione
                
                if rename_column(col_id, col_name, new_title):
                    print(f"   ✅ {col_name} → {new_title}")
                    renamed += 1
        
        total_renamed += renamed
        if renamed > 0:
            print(f"   → Zmieniono {renamed} nazw\n")
        else:
            print(f"   → Brak zmian (już ustawione)\n")
    
    print(f"\n🚀 Gotowe! Zmieniono łącznie {total_renamed} nazw kolumn.")


if __name__ == "__main__":
    main()
