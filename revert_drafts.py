from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from app.database import Lead, Client, Campaign
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
session = Session(engine)

# Szukamy leadów z dzisiaj, oznaczonych jako SENT, gdzie step_number=1
today_start = datetime.now(timezone.utc) - timedelta(hours=24)

leads_to_revert = session.query(Lead).filter(
    Lead.status == "SENT",
    Lead.step_number == 1,
    Lead.sent_at >= today_start
).all()

count = 0
for lead in leads_to_revert:
    lead.status = "DRAFTED"
    lead.sent_at = None
    count += 1

session.commit()
print(f"✅ Cofnięto {count} e-maili ze statusu 'SENT' z powrotem do 'DRAFTED'. Bot spróbuje je za moment ponownie wgrywać na pocztę!")
