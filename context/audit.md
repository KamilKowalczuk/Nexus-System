 KRYTYCZNE-03: del _smtp_password nie zeruje pamięci
Pliki: app/agents/sender.py, app/agents/inbox.py
python_smtp_password = decrypt_credential(client.smtp_password or "")
# ... użycie ...
del _smtp_password  # ← NIE zeruje pamięci!
W CPython del jedynie usuwa referencję. String pozostaje w pamięci do garbage collection, co może trwać nieznacznie lub bardzo długo. W przypadku memory dump (crash, core dump, swap file) — hasło SMTP jest czytelne.
Realność zagrożenia: Średnia — wymaga dostępu do pamięci procesu. Ale przy SaaS z wieloma klientami na jednej maszynie, jest to wielokrotnie istotniejsze.
FIX — użyj bytearray który da się nadpisać:
pythonimport ctypes

def secure_wipe(s: str) -> None:
    """Best-effort zerowanie stringa w pamięci CPython."""
    if not s:
        return
    try:
        # CPython internals: nadpisujemy bufor stringa zerami
        str_addr = id(s)
        # PyUnicodeObject header offset varies; for ASCII compact: 48 bytes on 64-bit
        buf_offset = 48
        ctypes.memset(str_addr + buf_offset, 0, len(s))
    except Exception:
        pass  # Non-CPython lub inny layout — silent fail

# Użycie:
_smtp_password = decrypt_credential(client.smtp_password or "")
try:
    server.login(sender_email, _smtp_password)
finally:
    secure_wipe(_smtp_password)
    del _smtp_password
Uwaga: To hack na CPython internals. Dla produkcyjnego rozwiązania rozważ przejście na SecretStr z Pydantic lub trzymanie credentiali w tmpfs-backed buffer.

🟠 WYSOKIE-06: datetime.utcnow() — Deprecated w Python 3.12+
Pliki: app/scheduler.py, app/rodo_manager.py, app/database.py, app/agents/inbox.py
datetime.utcnow() jest deprecated od Python 3.12 i zwraca naive datetime (bez tzinfo). Miksujesz datetime.now() (local time) z datetime.utcnow() (UTC ale naive) w różnych częściach systemu, co tworzy ciche przesunięcie czasowe przy follow-up delays i okienku wysyłkowym.
Przykład: scheduler.py używa datetime.utcnow() do porównania z lead.sent_at, ale main.py ustawia lead.sent_at = datetime.now() (czas lokalny). W Polsce = różnica 1-2h w zależności od DST.
FIX — globalny:
pythonfrom datetime import datetime, timezone

# Wszędzie zamiast datetime.utcnow():
datetime.now(timezone.utc)

# Wszędzie zamiast datetime.now() (gdy potrzebujesz UTC):
datetime.now(timezone.utc)

🟠 WYSOKIE-07: Brak Connection Pool Timeout na IMAP
Plik: app/agents/inbox.py
pythonmail = imaplib.IMAP4_SSL(client.imap_server, client.imap_port or 993, timeout=10)
Timeout 10s jest na connect — ale nie ma timeoutu na operacje (search, fetch). Jeśli serwer IMAP zawiesza się po połączeniu (np. anty-spam throttling), wątek asyncio jest zablokowany w asyncio.to_thread() w nieskończoność, zjadając slot z puli 20 workerów.
FIX:
pythonimport socket

mail = imaplib.IMAP4_SSL(client.imap_server, client.imap_port or 993, timeout=10)
mail.socket().settimeout(30)  # 30s timeout na KAŻDĄ operację I/O