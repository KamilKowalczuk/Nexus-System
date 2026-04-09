from app.database import engine
from sqlalchemy import text

def fix_all_sequences():
    tables = [
        "clients",
        "campaigns",
        "leads",
        "global_companies",
        "campaign_statistics",
        "briefs",
        "orders"
    ]
    
    print("🔧 Naprawa liczników ID (sekwencji) w bazie danych...")
    
    with engine.connect() as conn:
        for table in tables:
            try:
                # Sprawdź czy tabela istnieje i pobierz MAX(id)
                res = conn.execute(text(f"SELECT MAX(id) FROM {table}")).fetchone()
                max_id = res[0] if res and res[0] is not None else 0
                
                # Ustaw sekwencję (standardowa nazwa w Postgres: tabela_id_seq)
                seq_name = f"{table}_id_seq"
                conn.execute(text(f"SELECT setval('{seq_name}', {max_id + 1}, false)"))
                print(f"✅ {table}: ustawiono na {max_id}")
            except Exception as e:
                print(f"⚠️ Pominiecie {table}: {e}")
        
        conn.commit()
    
    print("\n🚀 Wszystkie liczniki zostały zsynchronizowane!")

if __name__ == "__main__":
    fix_all_sequences()
