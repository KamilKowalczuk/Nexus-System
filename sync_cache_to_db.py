import os
import json
import logging
from datetime import datetime
from app.redis_client import redis_client
from app.database import SessionLocal, GlobalCompany

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_cache")

def sync():
    # 1. Pobierz wszystkie klucze firm z Redis
    keys = redis_client.keys("company:scraped:*")
    logger.info(f"🔍 Znaleziono {len(keys)} wpisów w cache Redis.")
    
    session = SessionLocal()
    added = 0
    skipped = 0
    
    try:
        for key in keys:
            data = redis_client.get_json(key)
            if not data or 'domain' not in data:
                continue
            
            domain = data['domain'].lower().strip()
            
            # 2. Sprawdź czy firma już jest w bazie Postgres
            exists = session.query(GlobalCompany).filter_by(domain=domain).first()
            if exists:
                skipped += 1
                continue
            
            # 3. Mapowanie danych z cache do modelu DB
            # Redis cache przechowuje rozszerzony format Firecrawl
            new_company = GlobalCompany(
                domain=domain,
                name=data.get('name', domain),
                tech_stack=data.get('tech_stack', []),
                decision_makers=data.get('decision_makers', []),
                pain_points=data.get('pain_points', []),
                hiring_status=data.get('hiring_status'),
                is_active=True,
                has_mx_records=data.get('has_mx_records', False),
                last_scraped_at=datetime.fromisoformat(data['scraped_at']) if 'scraped_at' in data else datetime.now(),
                quality_score=data.get('quality_score', 0)
            )
            
            session.add(new_company)
            added += 1
            
            # Commit co 20 rekordów dla wydajności
            if added % 20 == 0:
                session.commit()
                logger.info(f"📥 Zsynchronizowano... (+{added})")

        session.commit()
        logger.info(f"✅ SYNCHRONIZACJA ZAKOŃCZONA: Dodano nowych firm: {added}, Pominięto (już były): {skipped}")
        
    except Exception as e:
        logger.error(f"💥 Błąd podczas synchronizacji: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    sync()
