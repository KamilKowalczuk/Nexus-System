import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# Ładujemy zmienne (żeby pobrać hasło, jeśli masz je w .env)
load_dotenv()

# KONFIGURACJA ZGODNA Z TWOIM DOCKER-COMPOSE
CONTAINER_NAME = "agency_db"  # To nazwa z Twojego pliku yml
DB_USER = "nexus"             # To user z Twojego pliku yml
DB_NAME = "agency_os"         # To baza z Twojego pliku yml

# Hasło bierzemy z env lub wpisz na sztywno jeśli wolisz, 
# ale zakładam że w .env masz to samo co w compose.
DB_PASS = os.getenv("POSTGRES_PASSWORD", "nexus_password") 

BACKUP_DIR = "backups"

def create_backup():
    # 1. Folder
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    # 2. Nazwa pliku
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{BACKUP_DIR}/titan_backup_{timestamp}.sql"

    print(f"⏳ Pobieram dane z kontenera '{CONTAINER_NAME}'...")

    # 3. KOMENDA (Docker Exec)
    # Wchodzimy do działającego kontenera i odpalamy pg_dump
    cmd = [
        "docker", "exec", 
        "-e", f"PGPASSWORD={DB_PASS}", # Przekazujemy hasło do środka
        CONTAINER_NAME,                # Nazwa kontenera
        "pg_dump", 
        "-U", DB_USER, 
        "--clean", 
        "--if-exists",
        DB_NAME
    ]

    try:
        # Otwieramy plik na dysku hosta (Twoim Archu) i przekierowujemy tam wynik z Dockera
        with open(filename, "w") as f:
            subprocess.run(cmd, stdout=f, check=True)

        size = os.path.getsize(filename) / (1024 * 1024)
        print(f"✅ SUKCES! Backup gotowy: {filename}")
        print(f"📊 Rozmiar: {size:.2f} MB")

    except subprocess.CalledProcessError as e:
        print(f"❌ Błąd: Upewnij się, że kontener '{CONTAINER_NAME}' jest uruchomiony!")
        print(f"   Detale: {e}")
    except Exception as e:
        print(f"❌ Inny błąd: {e}")

if __name__ == "__main__":
    create_backup()