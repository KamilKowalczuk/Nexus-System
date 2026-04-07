import os
import subprocess
import sys
from dotenv import load_dotenv

# Ładujemy zmienne
load_dotenv()

# KONFIGURACJA (Musi pasować do docker-compose)
CONTAINER_NAME = "agency_db"
DB_USER = "nexus"
DB_NAME = "agency_os"

BACKUP_DIR = "backups"

def restore_database():
    # 1. Sprawdź czy folder istnieje
    if not os.path.exists(BACKUP_DIR):
        print(f"❌ Folder {BACKUP_DIR} nie istnieje!")
        return

    # 2. Pobierz listę plików .sql
    files = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".sql")]
    files.sort(reverse=True) # Najnowsze na górze

    if not files:
        print("❌ Brak plików .sql w folderze backups/")
        return

    print("📂 Dostępne kopie zapasowe:")
    for idx, f in enumerate(files):
        print(f"   [{idx}] {f}")

    # 3. Wybór pliku
    try:
        choice = input("\n🔢 Wybierz numer pliku do przywrócenia (domyślnie 0 - najnowszy): ")
        if choice == "": choice = 0
        file_index = int(choice)
        selected_file = files[file_index]
    except (ValueError, IndexError):
        print("❌ Nieprawidłowy wybór.")
        return

    full_path = os.path.join(BACKUP_DIR, selected_file)
    print(f"\n⏳ Przywracam bazę z pliku: {selected_file}...")
    print("   ⚠️  To nadpisze obecne dane w bazie!")

    # 4. KOMENDA (Docker Exec + Pipe)
    # cat plik.sql | docker exec -i agency_db psql -U nexus -d agency_os
    
    # Budujemy komendę psql wewnątrz dockera
    docker_cmd = [
        "docker", "exec", "-i", 
        CONTAINER_NAME, 
        "psql", 
        "-U", DB_USER, 
        "-d", DB_NAME
    ]

    try:
        # Otwieramy plik .sql do odczytu
        with open(full_path, "r") as f:
            # Puszczamy zawartość pliku na wejście (stdin) procesu dockera
            subprocess.run(docker_cmd, stdin=f, check=True)
            
        print("\n✅ SUKCES! Baza danych została przywrócona.")
        print("🚀 Możesz uruchomić TITAN OS.")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ BŁĄD PRZYWRACANIA: {e}")
        print("💡 Sprawdź czy kontener 'agency_db' działa (docker ps).")

if __name__ == "__main__":
    restore_database()