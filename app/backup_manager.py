import os
import re
import json
import shutil
import textwrap
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("nexus_backup")


class BackupManager:
    def __init__(self, backup_dir="files/backups", max_backups=30):
        self.backup_dir = Path(os.getcwd()) / backup_dir
        self.max_backups = max_backups
        self.db_url = os.getenv("DATABASE_URL")
        self.gcs_bucket = os.getenv("GCS_BUCKET_NAME", "").strip() or None

        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_timestamp(self):
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _get_gcs_credentials(self):
        """
        Pobiera i naprawia (jeśli trzeba) klucze GCP z .env.
        Logika zsynchronizowana z app/kms_client.py (PEM repair).
        """
        from google.oauth2 import service_account

        # 1. Pobierz dane z env i wyczyść ewentualne spacje
        project_id = os.getenv("GCP_PROJECT_ID", "").strip()
        client_email = os.getenv("GCP_CLIENT_EMAIL", "").strip()
        raw_key = os.getenv("GCP_PRIVATE_KEY", "").strip()

        if not all([project_id, client_email, raw_key]):
            return None

        # 2. Napraw klucz prywatny (PEM format)
        pk = raw_key.replace('"', "").replace("\\n", "\n")
        if "-----BEGIN" in pk and "\n" not in pk:
            b64_data = re.sub(r"-----.*?-----", "", pk).replace(" ", "")
            lines = ["-----BEGIN PRIVATE KEY-----"]
            lines.extend(textwrap.wrap(b64_data, 64))
            lines.append("-----END PRIVATE KEY-----")
            pk = "\n".join(lines)

        return service_account.Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": project_id,
                "client_email": client_email,
                "private_key": pk,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

    def _rotate_backups(self):
        """Usuwa najstarsze lokalne backupy, jeśli przekroczymy limit (Złota Piątka)."""
        try:
            files = sorted(self.backup_dir.glob("backup_*"), key=os.path.getmtime)
            if len(files) > self.max_backups:
                to_delete = len(files) - self.max_backups
                for i in range(to_delete):
                    files[i].unlink()
                    logger.info(f"♻️ [ROTATION] Usunięto stary backup lokalny: {files[i].name}")
        except Exception as e:
            logger.error(f"❌ Błąd rotacji backupów lokalnych: {e}")

    def _rotate_gcs_backups(self):
        """Usuwa najstarsze backupy z GCS, zostawiając tylko 5 najnowszych."""
        if not self.gcs_bucket:
            return

        try:
            from google.cloud import storage
            
            credentials = self._get_gcs_credentials()
            if not credentials:
                return

            gcs_client = storage.Client(project=os.getenv("GCP_PROJECT_ID"), credentials=credentials)
            bucket = gcs_client.bucket(self.gcs_bucket)
            
            # Pobierz listę blobów w folderze nexus-backups/ posortowaną po dacie
            blobs = list(bucket.list_blobs(prefix="nexus-backups/"))
            blobs.sort(key=lambda x: x.updated)

            if len(blobs) > self.max_backups:
                to_delete = len(blobs) - self.max_backups
                for i in range(to_delete):
                    logger.info(f"♻️ [GCS ROTATION] Usuwam stary backup z chmury: {blobs[i].name}")
                    blobs[i].delete()
        except Exception as e:
            logger.warning(f"⚠️ [GCS ROTATION] Nie udało się wyczyścić starych backupów w chmurze: {e}")

    def _upload_to_gcs(self, local_path: Path) -> bool:
        """Wysyła plik backupu do Google Cloud Storage."""
        if not self.gcs_bucket:
            logger.warning("⚠️ [GCS] Brak GCS_BUCKET_NAME — pomijam upload do chmury.")
            return False

        try:
            from google.cloud import storage

            credentials = self._get_gcs_credentials()
            if not credentials:
                logger.error("❌ [GCS] Brak wymaganych kluczy GCP w .env (GCP_PROJECT_ID, client_email, private_key)")
                return False

            gcs_client = storage.Client(project=os.getenv("GCP_PROJECT_ID"), credentials=credentials)
            bucket = gcs_client.bucket(self.gcs_bucket)
            blob_name = f"nexus-backups/{local_path.name}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(local_path))

            logger.info(f"☁️ [GCS] Upload OK: gs://{self.gcs_bucket}/{blob_name}")
            
            # Po udanym uploadzie, wyczyść stare backupy w chmurze
            self._rotate_gcs_backups()
            return True

        except Exception as e:
            logger.warning(f"⚠️ [GCS] Upload nieudany: {e}")
            return False

    def _python_sql_backup(self, timestamp: str) -> bool:
        """Awaryjny backup całej bazy przez SQLAlchemy."""
        try:
            from sqlalchemy import create_engine, text, inspect as sa_inspect

            engine = create_engine(self.db_url)
            dest_name = f"backup_sql_python_{timestamp}.sql"
            dest_path = self.backup_dir / dest_name

            with engine.connect() as conn:
                inspector = sa_inspect(engine)
                tables = inspector.get_table_names()

                total_rows = 0
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(f"-- NEXUS BACKUP (Python fallback)\n")
                    for table in tables:
                        try:
                            rows = conn.execute(text(f'SELECT * FROM "{table}"')).fetchall()
                            cols = [c["name"] for c in inspector.get_columns(table)]
                            for row in rows:
                                vals = []
                                for v in row:
                                    if v is None: vals.append("NULL")
                                    elif isinstance(v, (dict, list)): vals.append("'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'")
                                    elif isinstance(v, bool): vals.append("TRUE" if v else "FALSE")
                                    elif isinstance(v, (int, float)): vals.append(str(v))
                                    else: vals.append("'" + str(v).replace("'", "''") + "'")
                                f.write(f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({", ".join(vals)});\n')
                                total_rows += 1
                        except Exception: continue

            size_bytes = dest_path.stat().st_size
            if size_bytes < 100:
                dest_path.unlink()
                return False

            logger.info(f"✅ [BACKUP] Python SQL OK: {dest_name} ({size_bytes/1024:.1f} KB)")
            self._rotate_backups()
            self._upload_to_gcs(dest_path)
            return True
        except Exception as e:
            logger.error(f"❌ [BACKUP] Python fallback FAILED: {e}")
            return False

    def perform_backup(self) -> bool:
        """Główna metoda backupu (pg_dump + Python fallback)."""
        if not self.db_url:
            return False

        timestamp = self._get_timestamp()

        try:
            if self.db_url.startswith("sqlite"):
                # SQLite handling
                db_path_str = self.db_url.replace("sqlite:///", "")
                source_path = Path(db_path_str)
                if source_path.exists():
                    dest_name = f"backup_sqlite_{timestamp}.db"
                    dest_path = self.backup_dir / dest_name
                    shutil.copy2(source_path, dest_path)
                    self._rotate_backups()
                    self._upload_to_gcs(dest_path)
                    return True
                return False

            elif self.db_url.startswith("postgresql") or self.db_url.startswith("postgres"):
                pg_dump_bin = shutil.which("pg_dump")
                pg_dump_ok = False

                if pg_dump_bin:
                    parsed = urlparse(self.db_url)
                    db_name = parsed.path.lstrip("/")
                    dest_name = f"backup_pg_{db_name}_{timestamp}.dump"
                    dest_path = self.backup_dir / dest_name

                    env = os.environ.copy()
                    if parsed.password:
                        env["PGPASSWORD"] = parsed.password

                    cmd = [
                        pg_dump_bin, "-h", parsed.hostname or "localhost",
                        "-p", str(parsed.port or 5432), "-U", parsed.username or "postgres",
                        "-F", "c", "-b", "-f", str(dest_path), db_name,
                    ]

                    process = subprocess.run(cmd, env=env, capture_output=True, text=True)
                    if process.returncode == 0 and dest_path.exists() and dest_path.stat().st_size >= 1024:
                        logger.info(f"✅ [BACKUP] pg_dump OK: {dest_name}")
                        self._rotate_backups()
                        self._upload_to_gcs(dest_path)
                        pg_dump_ok = True
                    else:
                        if dest_path.exists(): dest_path.unlink()

                if not pg_dump_ok:
                    logger.info("🔄 [BACKUP] Falling back to Python SQL...")
                    return self._python_sql_backup(timestamp)

                return True
            return False
        except Exception as e:
            logger.error(f"❌ Błąd krytyczny backupu: {e}")
            return False


backup_manager = BackupManager()
