"""
Migracja: Dodanie kolumn LLM model config do tabeli clients.
Uruchom raz po wdrożeniu multi-model support.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Brak DATABASE_URL w .env")

engine = create_engine(DATABASE_URL)

MIGRATION_SQL = [
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS scout_model VARCHAR DEFAULT 'gemini-3.1-flash-lite-preview';",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS researcher_model VARCHAR DEFAULT 'gemini-3.1-flash-lite-preview';",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS writer_model VARCHAR DEFAULT 'gemini-3.1-flash-lite-preview';",
]

if __name__ == "__main__":
    with engine.connect() as conn:
        for sql in MIGRATION_SQL:
            print(f"  ▶ {sql}")
            conn.execute(text(sql))
        conn.commit()
    print("\n✅ Migracja zakończona. Kolumny LLM model config dodane.")
