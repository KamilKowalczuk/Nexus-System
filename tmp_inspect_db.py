import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv('.env')

from app.database import GlobalCompany, Lead, Client, Campaign

db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print("No DATABASE_URL")
    sys.exit(1)

engine = create_engine(db_url)
session = Session(engine)

print("--- Checking MEDKOL ---")
medkol = session.query(GlobalCompany).filter(GlobalCompany.domain.ilike('%medkol%')).all()
for c in medkol:
    print(f"Company ID: {c.id}, Name: {c.name}, Domain: {c.domain}")
    print(f"Summary: {c.industry}")
    for lead in c.leads:
        print(f"   Lead ID: {lead.id}, Status: {lead.status}, target_email: {lead.target_email}")
        print(f"   AI Summary: {lead.ai_analysis_summary}")
        print(f"   Generated Body: {lead.generated_email_body[:200] if lead.generated_email_body else 'None'}")
    for lead in c.leads:
        print(f"   Lead ID: {lead.id}, Status: {lead.status}, target_email: {lead.target_email}")
        print(f"   AI Summary: {lead.ai_analysis_summary}")
        print(f"   Generated Body: {lead.generated_email_body[:200] if lead.generated_email_body else 'None'}")

print("\n--- Checking Clients ---")
clients = session.query(Client).all()
for cl in clients:
    print(f"Client: {cl.name}, ICP: {cl.ideal_customer_profile}")

