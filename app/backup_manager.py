import os
import shutil
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("nexus_backup")


class BackupManager:
    def __init__(self, backup_dir="files/backups", max_backups=20):
        self.backup_dir = Path(os.getcwd()) / backup_dir
        self.max_backups = max_backups
        self.db_url = os.getenv("DATABASE_URL")
        self.gcs_bucket = os.getenv("GCS_BUCKET_NAME")

        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_timestamp(self):
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _rotate_backups(self):
        """Usuwa najstarsze lokalne backupy, jeśli przekroczymy limit."""
        try:
            files = sorted(self.backup_dir.glob("backup_*"), key=os.path.getmtime)
            if len(files) > self.max_backups:
                to_delete = len(files) - self.max_backups
                for i in range(to_delete):
                    files[i].unlink()
                    logger.info(f"♻️ [ROTATION] Usunięto stary backup: {files[i].name}")
        except Exception as e:
            logger.error(f"❌ Błąd rotacji backupów: {e}")

    def _upload_to_gcs(self, local_path: Path) -> bool:
        """
        Wysyła plik backupu do Google Cloud Storage.

        Używa tych samych credentiali GCP co KMS (GCP_CLIENT_EMAIL + GCP_PRIVATE_KEY).
        Backup trafia do: gs://{GCS_BUCKET_NAME}/nexus-backups/{filename}

        Returns:
            True jeśli upload się udał, False w przeciwnym wypadku.
        """
        if not self.gcs_bucket:
            logger.warning("⚠️ [GCS] Brak GCS_BUCKET_NAME — pomijam upload do chmury.")
            return False

        try:
            from google.cloud import storage
            from google.oauth2 import service_account

            private_key = os.environ["GCP_PRIVATE_KEY"].replace("\\n", "\n")
            credentials = service_account.Credentials.from_service_account_info(
                {
                    "type": "service_account",
                    "project_id": os.environ["GCP_PROJECT_ID"],
                    "client_email": os.environ["GCP_CLIENT_EMAIL"],
                    "private_key": private_key,
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )

            gcs_client = storage.Client(
                project=os.environ["GCP_PROJECT_ID"],
                credentials=credentials,
            )
            bucket = gcs_client.bucket(self.gcs_bucket)
            blob_name = f"nexus-backups/{local_path.name}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(local_path))

            logger.info(f"☁️ [GCS] Upload OK: gs://{self.gcs_bucket}/{blob_name}")
            return True

        except ImportError:
            logger.warning("⚠️ [GCS] Brak biblioteki google-cloud-storage. Zainstaluj: pip install google-cloud-storage")
            return False
        except KeyError as e:
            logger.warning(f"⚠️ [GCS] Brak zmiennej środowiskowej GCP: {e} — pomijam upload.")
            return False
        except Exception as e:
            logger.error(f"❌ [GCS] Błąd uploadu: {e}")
            return False

    def perform_backup(self) -> bool:
        """
        Wykonuje pełną kopię bazy danych (pg_dump całej bazy — Nexus + PayloadCMS)
        i opcjonalnie wysyła do Google Cloud Storage.
        """
        if not self.db_url:
            logger.error("❌ Brak DATABASE_URL w .env")
            return False

        timestamp = self._get_timestamp()

        try:
            # 1. Obsługa SQLite (lokalny plik)
            if self.db_url.startswith("sqlite"):
                db_path_str = self.db_url.replace("sqlite:///", "")
                source_path = Path(db_path_str)

                if not source_path.exists():
                    source_path = Path(os.getcwd()) / db_path_str

                if source_path.exists():
                    dest_name = f"backup_sqlite_{timestamp}.db"
                    dest_path = self.backup_dir / dest_name
                    shutil.copy2(source_path, dest_path)
                    logger.info(f"✅ [BACKUP] SQLite zapisany: {dest_name}")
                    self._rotate_backups()
                    self._upload_to_gcs(dest_path)
                    return True
                else:
                    logger.error(f"❌ Nie znaleziono pliku bazy SQLite: {source_path}")
                    return False

            # 2. Obsługa PostgreSQL — pg_dump CAŁEJ bazy (Nexus + PayloadCMS)
            elif self.db_url.startswith("postgresql") or self.db_url.startswith("postgres"):
                parsed = urlparse(self.db_url)
                db_name = parsed.path.lstrip("/")
                user = parsed.username
                password = parsed.password
                host = parsed.hostname
                port = parsed.port or 5432

                dest_name = f"backup_pg_{db_name}_{timestamp}.dump"
                dest_path = self.backup_dir / dest_name

                env = os.environ.copy()
                if password:
                    env["PGPASSWORD"] = password

                # pg_dump bez filtrów tabel/schematów = CAŁA baza (Nexus + Payload)
                cmd = [
                    "pg_dump",
                    "-h", host,
                    "-p", str(port),
                    "-U", user,
                    "-F", "c",  # Format custom (kompresowany, przywracany przez pg_restore)
                    "-b",       # Blobs
                    "-f", str(dest_path),
                    db_name,
                ]

                process = subprocess.run(cmd, env=env, capture_output=True, text=True)

                if process.returncode == 0:
                    size_mb = dest_path.stat().st_size / (1024 * 1024)
                    logger.info(
                        f"✅ [BACKUP] PostgreSQL zapisany: {dest_name} ({size_mb:.1f} MB)"
                    )
                    self._rotate_backups()
                    self._upload_to_gcs(dest_path)
                    return True
                else:
                    logger.error(f"❌ Błąd pg_dump: {process.stderr}")
                    return False

            else:
                logger.warning(f"⚠️ Nieobsługiwany typ bazy: {self.db_url[:30]}...")
                return False

        except Exception as e:
            logger.error(f"❌ Błąd krytyczny backupu: {e}")
            return False


# Singleton instance
backup_manager = BackupManager()
