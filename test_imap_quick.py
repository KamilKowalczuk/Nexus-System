"""Szybki test IMAP po zmianie IP"""
import imaplib, os, time
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Client
from app.kms_client import decrypt_credential

eng = create_engine(os.environ['DATABASE_URL'])
s = Session(eng)
c = s.query(Client).filter(Client.name.ilike('%Koordynuj%')).first()
pw = decrypt_credential(c.smtp_password or '')

print(f"IP: ", end="")
os.system("curl -s ifconfig.me")
print()

# Test 1: Port 143 + STARTTLS
print("\n[1] Port 143 + STARTTLS...")
try:
    m = imaplib.IMAP4(c.imap_server, 143, timeout=15)
    print(f"    Welcome: {m.welcome}")
    if 'STARTTLS' in m.capabilities:
        m.starttls()
        print("    STARTTLS: OK")
    m.login(c.smtp_user, pw)
    print("    ✅ LOGIN OK!")
    st, fl = m.list()
    for f in fl:
        print(f"    📂 {f.decode('utf-8','ignore')}")
    
    # Test append
    test_msg = b"Subject: Test IMAP\r\nFrom: test@test.com\r\n\r\nTest"
    typ, dat = m.append("Kopie robocze", '(\\Draft \\Seen)', imaplib.Time2Internaldate(time.time()), test_msg)
    print(f"    APPEND: {typ} {dat}")
    m.logout()
except Exception as e:
    print(f"    ❌ {e}")

# Test 2: Port 993 SSL
print("\n[2] Port 993 SSL...")
try:
    m = imaplib.IMAP4_SSL(c.imap_server, 993, timeout=15)
    print(f"    Welcome: {m.welcome}")
    m.login(c.smtp_user, pw)
    print("    ✅ LOGIN OK!")
    m.logout()
except Exception as e:
    print(f"    ❌ {e}")

print("\n✅ DIAGNOSTYKA ZAKOŃCZONA")
