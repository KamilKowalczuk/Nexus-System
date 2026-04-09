import os
import sys
import re
from datetime import datetime
from sqlalchemy.sql import text
from app.database import SessionLocal, Client, Campaign, CampaignStatistics, Lead, GlobalCompany

# Ścieżka do wypakowanego SQL
SQL_FILE = "backup_data.sql"

def parse_copy_block(table_name):
    """Wyciąga dane z bloku COPY w pliku SQL."""
    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Znajdź początek COPY i koniec \.
    pattern = rf"COPY public\.{table_name} \((.*?)\) FROM stdin;\n(.*?)\n\\\."
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print(f"⚠️ Nie znaleziono danych dla tabeli {table_name}")
        return [], []
    
    columns = [c.strip() for c in match.group(1).split(',')]
    rows_raw = match.group(2).split('\n')
    
    data = []
    for row in rows_raw:
        if not row.strip(): continue
        # pg_dump używa \t jako separatora i \N dla NULL
        values = [None if v == '\\N' else v for v in row.split('\t')]
        if len(values) == len(columns):
            data.append(dict(zip(columns, values)))
    
    return columns, data

def merge_table(session, model_class, table_name, display_name):
    print(f"\n🔍 Przetwarzanie {display_name} ({table_name})...")
    cols, records = parse_copy_block(table_name)
    added = 0
    skipped = 0
    
    for rec in records:
        try:
            # 1. Sprawdzenie po ID (podstawowe)
            existing = session.get(model_class, int(rec['id']))
            if existing:
                skipped += 1
                continue
            
            # 2. Specyficzne sprawdzanie unikalności dla GlobalCompany (domena)
            if table_name == "global_companies":
                domain_exists = session.query(GlobalCompany).filter_by(domain=rec['domain']).first()
                if domain_exists:
                    skipped += 1
                    continue

            # 3. Przygotuj obiekt
            obj_data = {}
            for col in cols:
                val = rec[col]
                if val is None:
                    obj_data[col] = None
                    continue
                
                col_attr = getattr(model_class, col)
                col_type = str(col_attr.type).upper()
                
                if 'INTEGER' in col_type:
                    obj_data[col] = int(val)
                elif 'BOOLEAN' in col_type:
                    obj_data[col] = val == 't'
                elif 'FLOAT' in col_type or 'NUMERIC' in col_type:
                    obj_data[col] = float(val)
                elif 'JSONB' in col_type:
                    import json
                    # Unescape JSON string if needed (pg_dump format)
                    try:
                        obj_data[col] = json.loads(val.replace('\\"', '"'))
                    except:
                        obj_data[col] = val
                else:
                    obj_data[col] = val

            new_obj = model_class(**obj_data)
            session.add(new_obj)
            session.flush() # Sprawdź błędy unikalności przed commitem
            added += 1
        except Exception as e:
            session.rollback()
            skipped += 1
            # print(f"⚠️ Pominięto rekord ID {rec.get('id', '?')}: {e}") # Debugging

    session.commit()
    print(f"✅ Zakończono: Dodano {added}, Pominięto {skipped}")

def main():
    session = SessionLocal()
    try:
        # Kolejność ważna ze względu na FK
        merge_table(session, Client, "clients", "Klientów")
        merge_table(session, Campaign, "campaigns", "Kampanii")
        merge_table(session, CampaignStatistics, "campaign_statistics", "Statystyk")
        # Global companies (żeby leady miały do czego pić)
        merge_table(session, GlobalCompany, "global_companies", "Firm")
        # Leady na końcu
        merge_table(session, Lead, "leads", "Leadów")
        
        print("\n🚀 Fuzja zakończona sukcesem!")
    except Exception as e:
        print(f"\n💥 KRYTYCZNY BŁĄD: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()
