import sys
import socket
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Client
import os
import time
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
session = Session(engine)

client = session.query(Client).filter(Client.name.ilike('%Koordynuj%')).first()
if not client:
    print("Client not found")
    sys.exit(1)

print(f"Client: {client.name}")
print(f"IMAP Server: {client.imap_server}")
print(f"IMAP Port: {client.imap_port}")

if not client.imap_server:
    print("No IMAP server configured")
    sys.exit(0)

# Check socket connection
print("\nTesting raw socket connection...")
try:
    start = time.time()
    s = socket.create_connection((client.imap_server, client.imap_port or 993), timeout=10)
    print(f"Socket connection successful in {time.time() - start:.2f}s")
    s.close()
except Exception as e:
    print(f"Socket connection failed: {e}")

# Check SSL connection and Folders
print("\nTesting SSL connection and Login...")
try:
    from app.kms_client import decrypt_credential
    import imaplib
    
    start = time.time()
    mail = imaplib.IMAP4_SSL(client.imap_server, client.imap_port or 993, timeout=15)
    print(f"SSL connection successful in {time.time() - start:.2f}s")
    
    _pass = decrypt_credential(client.smtp_password or "")
    mail.login(client.smtp_user, _pass)
    print("Login successful!")
    
    status, folders = mail.list()
    print("Folders:")
    for f in folders:
        print("  ", f)
        
    mail.logout()
except Exception as e:
    print(f"IMAP Test failed: {e}")
