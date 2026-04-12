from sqlalchemy import text
from app.database import engine, Base


# ---------------------------------------------------------------------------
# MIGRACJE KOLUMN (dla istniejących baz danych)
# ---------------------------------------------------------------------------
# Uwaga: Base.metadata.create_all() tworzy NOWE tabele, ale nie dodaje kolumn
# do już istniejących. Poniższe migracje używają "ADD COLUMN IF NOT EXISTS"
# (składnia PostgreSQL 9.6+), więc są bezpieczne do wielokrotnego uruchamiania.

_COLUMN_MIGRATIONS = [
    # Tabela: opt_outs — migracja schematu (email_hash → value_hash + entry_type)
    # RENAME jest idempotentne tylko jeśli kolumna istnieje — obsługujemy błąd cicho
    "ALTER TABLE opt_outs RENAME COLUMN email_hash TO value_hash",
    "ALTER TABLE opt_outs ADD COLUMN IF NOT EXISTS entry_type VARCHAR(10) NOT NULL DEFAULT 'EMAIL'",

    # Tabela: clients — pola RODO/Compliance (dodane w Phase 3)
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS privacy_policy_url VARCHAR",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS opt_out_link VARCHAR",

    # Tabela: clients — pola warm-up (na wypadek starszych schematów)
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS warmup_enabled BOOLEAN DEFAULT FALSE",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS warmup_start_limit INTEGER DEFAULT 2",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS warmup_increment INTEGER DEFAULT 2",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS warmup_started_at TIMESTAMP",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS sending_mode VARCHAR DEFAULT 'DRAFT'",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS html_footer VARCHAR",

    # Tabela: leads — pola inbox/reply (na wypadek starszych schematów)
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS replied_at TIMESTAMP",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS reply_content VARCHAR",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS reply_sentiment VARCHAR",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS reply_analysis VARCHAR",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMP",

    # Tabela: clients — pola identyfikacyjne/CRM (dodane w Phase 4+)
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS nip VARCHAR",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS legal_name VARCHAR",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS payload_order_id INTEGER",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS payload_brief_id INTEGER",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'SALES'",

    # Tabela: clients — strategiczne DNA (tone, constraints, case studies)
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS tone_of_voice VARCHAR",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS negative_constraints TEXT",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS case_studies TEXT",

    # Tabela: clients — konfiguracja modeli LLM per-agent
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS scout_model VARCHAR DEFAULT 'gemini-3.1-flash-lite-preview'",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS researcher_model VARCHAR DEFAULT 'gemini-3.1-flash-lite-preview'",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS writer_model VARCHAR DEFAULT 'gemini-3.1-flash-lite-preview'",

    # Tabela: global_companies — numer telefonu z Google Maps
    "ALTER TABLE global_companies ADD COLUMN IF NOT EXISTS phone_number VARCHAR",

    # Tabela: global_companies — branża i adres z Google Maps
    "ALTER TABLE global_companies ADD COLUMN IF NOT EXISTS industry VARCHAR",
    "ALTER TABLE global_companies ADD COLUMN IF NOT EXISTS address VARCHAR",

    # Tabela: leads — UNIQUE constraint (campaign + company = max 1 lead)
    "ALTER TABLE leads ADD CONSTRAINT uq_lead_campaign_company UNIQUE (campaign_id, global_company_id)",

    # Tabela: leads — FOREIGN KEYS (relacje z campaigns i global_companies)
    "ALTER TABLE leads ADD CONSTRAINT fk_leads_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE",
    "ALTER TABLE leads ADD CONSTRAINT fk_leads_company FOREIGN KEY (global_company_id) REFERENCES global_companies(id) ON DELETE CASCADE",
]


def _run_migrations(conn) -> None:
    """
    Uruchamia bezpieczne (idempotentne) migracje kolumn.

    Każda instrukcja jest owinięta w SAVEPOINT, dzięki czemu błąd jednej migracji
    (np. RENAME nieistniejącej kolumny w świeżej bazie) nie przerywa całej transakcji
    i nie blokuje pozostałych migracji.
    """
    print("🔧 Uruchamiam migracje kolumn...")
    ok_count = 0
    skip_count = 0
    for i, sql in enumerate(_COLUMN_MIGRATIONS):
        sp = f"sp_migration_{i}"
        try:
            conn.execute(text(f"SAVEPOINT {sp}"))
            conn.execute(text(sql))
            conn.execute(text(f"RELEASE SAVEPOINT {sp}"))
            ok_count += 1
        except Exception as e:
            conn.execute(text(f"ROLLBACK TO SAVEPOINT {sp}"))
            skip_count += 1
            # Ignoruj "already exists" / "does not exist" — to normalne przy idempotentnych migracjach
            err_str = str(e)
            if "already exists" in err_str or "does not exist" in err_str:
                pass  # Kolumna już istnieje lub nie ma czego rename'ować — OK
            else:
                print(f"   ⚠️  {sql[:70]}...")
                print(f"        → {err_str[:120]}")

    print(f"   ✅ Migracje: {ok_count} wykonanych, {skip_count} pominiętych (już istnieją lub N/A)")


def init_db() -> None:
    print("🚀 Inicjalizacja Agency OS Database...")

    with engine.begin() as conn:
        # 1. Tworzenie NOWYCH tabel (istniejące są pomijane)
        Base.metadata.create_all(bind=engine)
        print("✅ Tabele sprawdzone / utworzone:")
        print("   - clients          (Client DNA)")
        print("   - global_companies (Knowledge Graph)")
        print("   - campaigns")
        print("   - leads")
        print("   - opt_outs         (RODO Blacklist — hash-only)")
        print("   - search_history")

        # 2. Migracje kolumn dla istniejących tabel
        _run_migrations(conn)

    print("\n✅ Baza danych gotowa do pracy.")


if __name__ == "__main__":
    init_db()
