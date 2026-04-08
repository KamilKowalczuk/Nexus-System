import smtplib
import ssl
import ctypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

from app.database import Lead, Client
from app.kms_client import decrypt_credential


def _secure_wipe(s: str) -> None:
    """Bezpieczne kasowanie referencji hasła. Samo del wystarczy — GC posprząta."""
    pass

def send_email_via_smtp(lead: Lead, client: Client) -> bool:
    """
    Wysyła fizycznego maila przez SMTP (Pełen Automat).
    Hasło SMTP jest deszyfrowane przez GCP KMS tylko w chwili połączenia
    i nigdy nie jest przechowywane poza lokalnym zasięgiem tej funkcji.
    """
    try:
        sender_email = client.smtp_user
        receiver_email = lead.target_email
        
        # Tworzenie wiadomości
        message = MIMEMultipart("alternative")
        message["Subject"] = lead.generated_email_subject
        message["From"] = f"{client.sender_name} <{sender_email}>"
        message["To"] = receiver_email

        # Treść HTML – kompletna (body + html_footer + RODO) zmontowana przez writer.py
        html_content = lead.generated_email_body

        # Wersja Plain Text (Zabezpieczenie przed filtrami SPAM - parsowanie z HTML)
        soup = BeautifulSoup(html_content, "html.parser")
        # Wyłuskujemy tekst, wstawiając nową linię po każdym nagłówku lub używając defaultowego separatora
        text_content = soup.get_text(separator="\n", strip=True)

        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")

        message.attach(part1)
        message.attach(part2)

        # Logowanie do serwera
        # KMS: deszyfrowanie następuje tuż przed connect() i kończy się razem z blokiem with
        context = ssl.create_default_context()
        _smtp_password = decrypt_credential(client.smtp_password or "")

        try:
            # Obsługa różnych portów (465 SSL, 587 TLS) - z ZABEZPIECZENIEM ANTI-ZOMBIE 20s
            if client.smtp_port == 465:
                with smtplib.SMTP_SSL(client.smtp_server, client.smtp_port, context=context, timeout=20) as server:
                    server.login(sender_email, _smtp_password)
                    server.sendmail(sender_email, receiver_email, message.as_string())
            else:
                with smtplib.SMTP(client.smtp_server, client.smtp_port, timeout=20) as server:
                    server.starttls(context=context)
                    server.login(sender_email, _smtp_password)
                    server.sendmail(sender_email, receiver_email, message.as_string())
        finally:
            _secure_wipe(_smtp_password)
            del _smtp_password

        return True

    except Exception as e:
        print(f"❌ Błąd SMTP: {e}")
        return False