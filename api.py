from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
import os
import signal
import subprocess
import time
import asyncio
from typing import Dict, Any, List

from fastapi import Security, HTTPException, status, Query
from fastapi.security.api_key import APIKeyHeader

# Setup ścieżek
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

PID_FILE = os.path.join(ROOT_DIR, 'engine.pid')
LOG_FILE = os.path.join(ROOT_DIR, 'engine.log')
HEARTBEAT_FILE = os.path.join(ROOT_DIR, 'engine.heartbeat')
_HEARTBEAT_TIMEOUT = 60
_ENGINE_START_GRACE = 120

# Baza danych i inne
from app.database import SessionLocal, Client, Campaign, Lead
from sqlalchemy import func

app = FastAPI(title="Nexus Engine API", description="Control API for Titan Bot Engine")

# CORS setup - zezwalamy payloadCMS dev i frontent build na loclhost i nexusagent.pl
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4321",
        "http://localhost:3000",
        "https://nexusagent.pl",
        "https://www.nexusagent.pl",
        "https://panel.nexusagent.pl"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_NAME = "X-Nexus-Api-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key_header: str = Security(api_key_header)):
    # Pobieramy klucz z pliku .env bota
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
    expected_key = os.getenv("NEXUS_ADMIN_KEY")
    
    if not expected_key:
        # Failsafe: jeśli zapomnisz dodać klucza, blokuje wszystko (bezpieczeństwo domyślne)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Brak NEXUS_ADMIN_KEY na serwerze.")
        
    if api_key_header == expected_key:
        return api_key_header
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nieważny klucz API Nexus")


def is_engine_running() -> bool:
    """Sprawdza czy silnik main.py jest żywy i aktywny."""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        try: os.remove(PID_FILE)
        except: pass
        try:
            if os.path.exists(HEARTBEAT_FILE): os.remove(HEARTBEAT_FILE)
        except: pass
        return False

    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, 'r') as f:
                ts = float(f.read().strip())
            if time.time() - ts > _HEARTBEAT_TIMEOUT:
                return False
            return True
        except (OSError, ValueError):
            pass

    try:
        pid_age = time.time() - os.path.getmtime(PID_FILE)
        return pid_age < _ENGINE_START_GRACE
    except Exception:
        return True


def start_engine_logic():
    """Uruchamia main.py jako proces tła."""
    if is_engine_running():
        return
    for f in (PID_FILE, HEARTBEAT_FILE):
        if os.path.exists(f):
            try: os.remove(f)
            except: pass
            
    try:
        from app import critical_monitor
        critical_monitor.clear_stop()
    except:
        pass

    try: open(LOG_FILE, 'w').close()
    except: pass

    log_handle = open(LOG_FILE, "a")
    process = subprocess.Popen(
        [sys.executable, "-u", "main.py"],
        cwd=ROOT_DIR,
        stdout=log_handle,
        stderr=log_handle,
    )
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
    except Exception as e:
        print(f"Błąd zapisu PID: {e}")


def stop_engine_logic():
    """Zatrzymuje silnik (SIGTERM) i sprząta pliki sterujące."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            print(f"Błąd zatrzymywania silnika: {e}")
        finally:
            try: os.remove(PID_FILE)
            except: pass

    if os.path.exists(HEARTBEAT_FILE):
        try: os.remove(HEARTBEAT_FILE)
        except: pass


def get_engine_logs(lines=200):
    if not os.path.exists(LOG_FILE): return "Brak logów."
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            recent = all_lines[-lines:]
            recent.reverse()
            return "".join(recent)
    except:
        return "Błąd odczytu."


@app.get("/api/engine/status")
def engine_status(api_key: str = Security(get_api_key)):
    running = is_engine_running()
    stopped = False
    stop_reason = ""
    if not running:
        try:
            from app import critical_monitor
            stopped, stop_reason = critical_monitor.is_stopped()
        except:
            pass
            
    return {
        "running": running,
        "critical_stop": stopped,
        "stop_reason": stop_reason,
    }


@app.post("/api/engine/start")
def start_engine(api_key: str = Security(get_api_key)):
    start_engine_logic()
    return {"status": "started"}


@app.post("/api/engine/stop")
def stop_engine(api_key: str = Security(get_api_key)):
    stop_engine_logic()
    return {"status": "stopped"}


@app.post("/api/engine/sync_briefs")
def sync_briefs(api_key: str = Security(get_api_key)):
    from app.brief_sync import sync_briefs_to_clients
    try:
        with SessionLocal() as session:
            result = sync_briefs_to_clients(session)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/engine/logs")
def engine_logs(lines: int = 200, api_key: str = Security(get_api_key)):
    return {"logs": get_engine_logs(lines)}


@app.websocket("/api/ws/logs")
async def websocket_logs(websocket: WebSocket, token: str = Query(None)):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
    expected_key = os.getenv("NEXUS_ADMIN_KEY")
    
    if not token or token != expected_key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await websocket.accept()
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("")
            
    log_file = open(LOG_FILE, "r", encoding="utf-8")
    log_file.seek(0, 2) # Go to end
    
    try:
        while True:
            line = log_file.readline()
            if not line:
                await asyncio.sleep(0.5)
                continue
            await websocket.send_text(line)
    except WebSocketDisconnect:
        print("Websocket disconnected")
    finally:
        log_file.close()

@app.get("/api/metrics")
def get_metrics(api_key: str = Security(get_api_key)):
    """Generates global metrics"""
    with SessionLocal() as session:
        c_new = session.query(Lead).filter(Lead.status == "NEW").count()
        c_ready = session.query(Lead).filter(Lead.status == "ANALYZED").count()
        c_draft = session.query(Lead).filter(Lead.status == "DRAFTED").count()
        today = time.strftime('%Y-%m-%d')
        sent_today = session.query(Lead).filter(
            Lead.status == "SENT",
            func.date(Lead.sent_at) == today
        ).count()
        
    return {
        "queue_new": c_new,
        "queue_analyzed": c_ready,
        "queue_drafted": c_draft,
        "sent_today": sent_today
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
