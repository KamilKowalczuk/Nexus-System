from app.kms_client import decrypt_credential
import imaplib
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Client
import os
import sys

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
session = Session(engine)

client = session.query(Client).filter(Client.name.ilike('%Koordynuj%')).first()
_pass = decrypt_credential(client.smtp_password or "")

try:
    mail = imaplib.IMAP4_SSL(client.imap_server, client.imap_port or 993, timeout=30)
    mail.socket().settimeout(30)
    mail.login(client.smtp_user, _pass)
    status, folders = mail.list()
    print("ALL FOLDERS:")
    for f in folders:
        print(f.decode('utf-8'))
        
    print("\nAttempting to find drafts...")
    # let's try appending a test draft to "Drafts"
    msg = b"Subject: Test Draft\\r\\n\\r\\nThis is a test draft."
    typ, dat = mail.append("Drafts", '(\\Draft)', None, msg)
    print("Append to 'Drafts' result:", typ, dat)
    
    mail.logout()
except Exception as e:
    print("ERROR:", e)
