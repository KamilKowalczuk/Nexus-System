import os
import json
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
            logger.warning(f"⚠️ [GCS] Upload pominięty: {e} — backup lokalny zachowany.")
            return False

    # =========================================================================
    # PYTHON SQL BACKUP (FALLBACK) — nie wymaga pg_dump, działa ZAWSZE
    # =========================================================================
    def _python_sql_backup(self, timestamp: str) -> bool:
        """
        Awaryjny backup całej bazy przez SQLAlchemy → plik .sql z INSERT-ami.
        Działa ZAWSZE, niezależnie od wersji pg_dump. Używany jako fallback
        gdy pg_dump zawiedzie (np. version mismatch).
        """
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
                    f.write(f"-- NEXUS BACKUP (Python SQLAlchemy fallback)\n")
                    f.write(f"-- Timestamp: {timestamp}\n")
                    f.write(f"-- Tables: {len(tables)}\n\n")

                    for table in tables:
                        try:
                            rows = conn.execute(text(f'SELECT * FROM "{table}"')).fetchall()
                            cols = [c["name"] for c in inspector.get_columns(table)]

                            f.write(f"\n-- TABLE: {table} ({len(rows)} rows)\n")

                            for row in rows:
                                vals = []
                                for v in row:
                                    if v is None:
                                        vals.append("NULL")
                                    elif isinstance(v, (dict, list)):
                                        vals.append("'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'")
                                    elif isinstance(v, bool):
                                        vals.append("TRUE" if v else "FALSE")
                                    elif isinstance(v, (int, float)):
                                        vals.append(str(v))
                                    else:
                                        vals.append("'" + str(v).replace("'", "''") + "'")
                                f.write(f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({", ".join(vals)});\n')
                                total_rows += 1
                        except Exception as table_err:
                            f.write(f"-- ERROR dumping {table}: {table_err}\n")
                            logger.warning(f"⚠️ [BACKUP] Pominięto tabelę {table}: {table_err}")

            size_bytes = dest_path.stat().st_size
            if size_bytes < 100:
                logger.error(f"❌ [BACKUP] Python SQL backup pusty ({size_bytes}B)!")
                dest_path.unlink()
                return False

            size_kb = size_bytes / 1024
            logger.info(
                f"✅ [BACKUP] Python SQL backup: {dest_name} ({size_kb:.1f} KB, "
                f"{total_rows} wierszy z {len(tables)} tabel)"
            )
            self._rotate_backups()

            gcs_ok = self._upload_to_gcs(dest_path)
            if not gcs_ok:
                logger.error("❌ Backup zapisany LOKALNIE, ale GCS upload FAILED!")
            return True

        except Exception as e:
            logger.error(f"❌ [BACKUP] Python SQL backup FAILED: {e}")
            return False

    # =========================================================================
    # GŁÓWNA METODA BACKUPU
    # =========================================================================
    def perform_backup(self) -> bool:
        """
        Wykonuje pełną kopię bazy danych.

        Strategia dwupoziomowa:
        1. pg_dump (natywny, kompresowany .dump) — najlepszy, ale wymaga
           zgodności wersji klienta i serwera PostgreSQL.
        2. Python SQL fallback (.sql z INSERT-ami) — działa ZAWSZE,
           używany automatycznie gdy pg_dump zawiedzie.

        Backup jest opcjonalnie wysyłany do Google Cloud Storage.
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

            # 2. Obsługa PostgreSQL — pg_dump + Python fallback
            elif self.db_url.startswith("postgresql") or self.db_url.startswith("postgres"):

                # === PRÓBA 1: pg_dump (natywny, najlepszy) ===
                pg_dump_bin = shutil.which("pg_dump")
                pg_dump_ok = False

                if pg_dump_bin:
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

                    cmd = [
                        pg_dump_bin,
                        "-h", host,
                        "-p", str(port),
                        "-U", user,
                        "-F", "c",
                        "-b",
                        "-f", str(dest_path),
                        db_name,
                    ]

                    process = subprocess.run(cmd, env=env, capture_output=True, text=True)

                    if process.returncode == 0 and dest_path.exists():
                        size_bytes = dest_path.stat().st_size
                        if size_bytes >= 1024:
                            size_mb = size_bytes / (1024 * 1024)
                            logger.info(f"✅ [BACKUP] pg_dump OK: {dest_name} ({size_mb:.2f} MB)")
                            self._rotate_backups()
                            gcs_ok = self._upload_to_gcs(dest_path)
                            if not gcs_ok:
                                logger.error("❌ Backup zapisany LOKALNIE, ale GCS upload FAILED!")
                            pg_dump_ok = True
                        else:
                            logger.error(
                                f"❌ [BACKUP] pg_dump stworzył pusty plik ({size_bytes}B)! "
                                f"Przechodzę na Python fallback."
                            )
                            dest_path.unlink()
                    else:
                        stderr_msg = process.stderr[:300] if process.stderr else "brak stderr"
                        logger.error(
                            f"❌ [BACKUP] pg_dump FAILED (code={process.returncode}): {stderr_msg}. "
                            f"Przechodzę na Python fallback."
                        )
                        if dest_path.exists():
                            dest_path.unlink()
                else:
                    logger.warning("⚠️ [BACKUP] pg_dump nie zainstalowany — używam Python fallback.")

                # === PRÓBA 2: Python SQL fallback (ZAWSZE działa) ===
                if not pg_dump_ok:
                    logger.info("🔄 [BACKUP] Uruchamiam Python SQL fallback...")
                    return self._python_sql_backup(timestamp)

                return True

            else:
                logger.warning(f"⚠️ Nieobsługiwany typ bazy: {self.db_url[:30]}...")
                return False

        except Exception as e:
            logger.error(f"❌ Błąd krytyczny backupu: {e}")
            return False


# Singleton instance
backup_manager = BackupManager()
