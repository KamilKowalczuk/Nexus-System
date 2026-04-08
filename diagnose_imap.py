"""
DIAGNOSTYKA IMAP v2 — fokus na SSL i login
"""
import socket
import ssl
import imaplib
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Client
from app.kms_client import decrypt_credential

DATABASE_URL = os.environ.get('DATABASE_URL')
eng = create_engine(DATABASE_URL)
session = Session(eng)
client = session.query(Client).filter(Client.name.ilike('%Koordynuj%')).first()

imap_host = client.imap_server
imap_port = client.imap_port or 993
smtp_user = client.smtp_user
password = decrypt_credential(client.smtp_password or "")

print("=" * 60)
print(f"Host:  {imap_host}:{imap_port}")
print(f"User:  {smtp_user}")
print(f"Pass:  {'*' * len(password)} (len={len(password)})")
print("=" * 60)

# ─── TEST A: imaplib domyślny ───
print("\n[A] imaplib.IMAP4_SSL (default)...")
try:
    m = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30)
    print(f"   Connected. Welcome: {m.welcome}")
    m.login(smtp_user, password)
    print(f"   ✅ LOGIN OK!")
    s, fl = m.list()
    print(f"   Folders: {[f.decode('utf-8','ignore') for f in fl]}")
    m.logout()
except Exception as e:
    print(f"   ❌ {type(e).__name__}: {e}")

# ─── TEST B: z własnym context (no verify) ───
print("\n[B] imaplib.IMAP4_SSL (no-verify context)...")
try:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    m = imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=ctx, timeout=30)
    print(f"   Connected. Welcome: {m.welcome}")
    m.login(smtp_user, password)
    print(f"   ✅ LOGIN OK!")
    s, fl = m.list()
    print(f"   Folders: {[f.decode('utf-8','ignore') for f in fl]}")
    m.logout()
except Exception as e:
    print(f"   ❌ {type(e).__name__}: {e}")

# ─── TEST C: ręczny socket + SSL + IMAP ───
print("\n[C] Ręczny socket → SSL → IMAP protocol...")
try:
    s = socket.create_connection((imap_host, imap_port), timeout=30)
    ctx = ssl.create_default_context()
    ss = ctx.wrap_socket(s, server_hostname=imap_host)
    print(f"   SSL OK. Cipher: {ss.cipher()[0]}, Proto: {ss.version()}")
    
    # Read IMAP greeting
    ss.settimeout(10)
    greeting = ss.recv(4096)
    print(f"   Greeting: {greeting.decode('utf-8','ignore').strip()}")
    
    # Send LOGIN
    login_cmd = f'A001 LOGIN {smtp_user} {password}\r\n'
    ss.sendall(login_cmd.encode('utf-8'))
    resp = ss.recv(4096)
    print(f"   Login response: {resp.decode('utf-8','ignore').strip()}")
    
    # LIST
    ss.sendall(b'A002 LIST "" "*"\r\n')
    time.sleep(1)
    resp = b""
    while True:
        try:
            chunk = ss.recv(4096)
            if not chunk:
                break
            resp += chunk
        except socket.timeout:
            break
    print(f"   Folders:\n{resp.decode('utf-8','ignore')}")
    
    ss.sendall(b'A003 LOGOUT\r\n')
    ss.close()
    print(f"   ✅ MANUAL TEST PASSED!")
except Exception as e:
    print(f"   ❌ {type(e).__name__}: {e}")

# ─── TEST D: openssl s_client info ───
print("\n[D] Checking openssl info...")
os.system(f"echo '' | timeout 5 openssl s_client -connect {imap_host}:{imap_port} -brief 2>&1 | head -5")

print("\n" + "=" * 60)
print("DIAGNOSTYKA ZAKOŃCZONA")
