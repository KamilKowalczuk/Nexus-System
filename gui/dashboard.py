import streamlit as st
import pandas as pd
import time
import sys
import os
import signal
import subprocess
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, exc

# --- IMPORTY BACKENDU ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app.database import engine, Client, Campaign, Lead, GlobalCompany
    from app.agents.strategy import generate_strategy
    from app.agents.scout import run_scout_async 
    from app.agents.researcher import analyze_lead
    from app.agents.writer import generate_email
    from app.scheduler import process_followups, save_draft_via_imap
    from app.agents.inbox import check_inbox
    from app.agents.reporter import create_pdf_report
    # Import logiki warm-up
    from app.warmup import calculate_daily_limit
except ImportError as e:
    st.error(f"❌ BŁĄD IMPORTÓW: Nie można załadować modułów backendu.\nDetale: {e}")
    st.stop()


# --- PHASE 2 DETECTION ---
PHASE2_ENABLED = False
cache_manager = None
rate_limiter = None
queue_manager = None

try:
    from app.cache_manager import cache_manager
    from app.rate_limiter import rate_limiter
    from app.queue_manager import queue_manager
    from app.redis_client import redis_client
    from app.tools import get_email_cache_stats
    PHASE2_ENABLED = True
except ImportError:
    pass  # Phase 2 not available

try:
    from app.model_factory import get_available_models, get_available_api_keys, DEFAULT_MODEL
    MODEL_FACTORY_OK = True
except ImportError:
    MODEL_FACTORY_OK = False

from app.kms_client import encrypt_credential, is_encrypted, is_kms_available
# ------------------------

# --- KONFIGURACJA UI ---
st.set_page_config(
    page_title="Agency OS | Titan Edition",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS (NEXUS Design System) ---
st.markdown("""
<style>
    /* === GOOGLE FONTS === */
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

    /* === BASE === */
    [data-testid="stApp"] {
        background-color: #0B0C10 !important;
        font-family: 'Inter', sans-serif !important;
    }

    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
    }

    /* === TYPOGRAFIA === */
    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #e2e8f0 !important;
        letter-spacing: -0.01em !important;
        font-weight: 700 !important;
    }
    h1 { font-size: 1.9rem !important; }
    h2 { font-size: 1.4rem !important; }
    h3, h4 { font-size: 1.1rem !important; font-weight: 600 !important; }

    /* === SIDEBAR === */
    [data-testid="stSidebar"] {
        background: #0a0b0f !important;
        border-right: 1px solid rgba(255,255,255,0.05) !important;
    }
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] .stMarkdown h3 {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.65rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.14em !important;
        text-transform: uppercase !important;
        color: #475569 !important;
    }
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.05) !important; }

    /* === METRIC CARDS === */
    [data-testid="metric-container"] {
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 14px !important;
        padding: 18px !important;
        box-shadow: none !important;
        transition: border-color 0.3s, box-shadow 0.3s !important;
    }
    [data-testid="metric-container"]:hover {
        border-color: rgba(12,234,237,0.22) !important;
        box-shadow: 0 0 18px rgba(12,234,237,0.07) !important;
    }
    [data-testid="stMetricLabel"] p {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 10px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
        color: #64748b !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 1.9rem !important;
        font-weight: 700 !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stMetricDelta"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
    }

    /* === BUTTONS === */
    .stButton > button {
        background: rgba(255,255,255,0.04) !important;
        color: #cbd5e1 !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        letter-spacing: 0.02em !important;
        transition: all 0.2s ease !important;
        padding: 0.5rem 1.25rem !important;
    }
    .stButton > button:hover {
        background: rgba(12,234,237,0.07) !important;
        border-color: rgba(12,234,237,0.3) !important;
        color: #0ceaed !important;
        box-shadow: 0 0 14px rgba(12,234,237,0.12) !important;
        transform: translateY(-1px) !important;
    }
    .stButton > button[kind="primary"] {
        background: #0ceaed !important;
        color: #0B0C10 !important;
        border-color: #0ceaed !important;
        font-weight: 700 !important;
        box-shadow: 0 0 20px rgba(12,234,237,0.28) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #0ceaed !important;
        color: #0B0C10 !important;
        box-shadow: 0 0 30px rgba(12,234,237,0.45) !important;
        filter: brightness(1.08) !important;
        transform: translateY(-1px) !important;
    }

    /* === TABS === */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        background: transparent !important;
        border-bottom: 1px solid rgba(255,255,255,0.07) !important;
        gap: 0 !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        background: transparent !important;
        color: #64748b !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 10.5px !important;
        font-weight: 500 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.09em !important;
        border-bottom: 2px solid transparent !important;
        padding: 0.7rem 1.2rem !important;
        transition: all 0.2s !important;
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        color: #0ceaed !important;
        border-bottom-color: #0ceaed !important;
        background: transparent !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab"]:hover {
        color: #94a3b8 !important;
    }

    /* === INPUTS === */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.09) !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
        transition: border-color 0.2s !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: rgba(12,234,237,0.4) !important;
        box-shadow: 0 0 12px rgba(12,234,237,0.07) !important;
    }
    [data-testid="stTextInput"] label,
    [data-testid="stTextArea"] label,
    [data-testid="stNumberInput"] label,
    .stSelectbox label, .stRadio label > span,
    .stCheckbox label > span {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 10.5px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.09em !important;
        color: #64748b !important;
        font-weight: 500 !important;
    }

    /* === SELECTBOX === */
    [data-baseweb="select"] > div {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.09) !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
    }
    [data-baseweb="popover"] [data-baseweb="menu"] {
        background: #111318 !important;
        border: 1px solid rgba(255,255,255,0.09) !important;
        border-radius: 10px !important;
    }
    [data-baseweb="option"] { color: #e2e8f0 !important; background: transparent !important; }
    [data-baseweb="option"]:hover,
    [data-baseweb="option"][aria-selected="true"] {
        background: rgba(12,234,237,0.08) !important;
        color: #0ceaed !important;
    }

    /* === EXPANDER === */
    [data-testid="stExpander"] {
        background: rgba(255,255,255,0.02) !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 12px !important;
    }
    [data-testid="stExpander"] summary {
        color: #94a3b8 !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 600 !important;
    }
    [data-testid="stExpander"] summary:hover { color: #e2e8f0 !important; }

    /* === FORM === */
    [data-testid="stForm"] {
        background: rgba(255,255,255,0.02) !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 14px !important;
        padding: 1.5rem !important;
    }

    /* === DATAFRAME === */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }

    /* === DIVIDER === */
    hr { border-color: rgba(255,255,255,0.06) !important; }

    /* === CAPTIONS === */
    [data-testid="stCaptionContainer"] p {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
        color: #475569 !important;
    }

    /* === CODE === */
    code {
        background: rgba(12,234,237,0.08) !important;
        color: #0ceaed !important;
        border-radius: 5px !important;
        padding: 2px 6px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 12px !important;
    }
    [data-testid="stCode"] {
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 10px !important;
    }

    /* === PROGRESS BAR === */
    [data-testid="stProgressBar"] > div > div {
        background: linear-gradient(90deg, #0ceaed, #9c27b0) !important;
        border-radius: 9999px !important;
    }
    [data-testid="stProgressBar"] > div {
        background: rgba(255,255,255,0.05) !important;
        border-radius: 9999px !important;
    }

    /* === ENGINE STATUS BOXES (custom HTML) === */
    .engine-status-box {
        padding: 11px 16px;
        border-radius: 10px;
        text-align: center;
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 700;
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 12px;
        border: 1px solid;
    }
    .status-online {
        background: rgba(34,197,94,0.08);
        color: #86efac;
        border-color: rgba(34,197,94,0.22);
        box-shadow: 0 0 14px rgba(34,197,94,0.09);
    }
    .status-offline {
        background: rgba(239,68,68,0.08);
        color: #fca5a5;
        border-color: rgba(239,68,68,0.22);
        box-shadow: 0 0 14px rgba(239,68,68,0.09);
    }

    /* === LIVE DOT === */
    @keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0.25; } }
    .live-dot { color: #ef4444; animation: blink 1.5s infinite; font-weight: bold; }

    /* === CONSOLE LOGS === */
    .console-logs {
        background: rgba(255,255,255,0.02);
        color: #94a3b8;
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        line-height: 1.65;
        padding: 16px;
        border-radius: 12px;
        height: 400px;
        overflow-y: scroll;
        white-space: pre-wrap;
        border: 1px solid rgba(255,255,255,0.06);
    }
    .console-logs::-webkit-scrollbar { width: 5px; }
    .console-logs::-webkit-scrollbar-track { background: transparent; }
    .console-logs::-webkit-scrollbar-thumb {
        background: rgba(12,234,237,0.18);
        border-radius: 9999px;
    }
    .console-logs::-webkit-scrollbar-thumb:hover { background: rgba(12,234,237,0.35); }

    /* === GLOBAL SCROLLBAR === */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(255,255,255,0.07);
        border-radius: 9999px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(12,234,237,0.25); }
</style>
""", unsafe_allow_html=True)

# --- ŚCIEŻKI I PLIKI STERUJĄCE ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FILES_DIR = os.path.join(ROOT_DIR, 'files')
PID_FILE = os.path.join(ROOT_DIR, 'engine.pid')
LOG_FILE = os.path.join(ROOT_DIR, 'engine.log')
HEARTBEAT_FILE = os.path.join(ROOT_DIR, 'engine.heartbeat')
_HEARTBEAT_TIMEOUT = 60    # sekund — jeśli brak heartbeatu >60s, silnik uznany za zawieszony
_ENGINE_START_GRACE = 120  # sekund — grace period przy starcie (backup+sync mogą zająć chwilę)

os.makedirs(FILES_DIR, exist_ok=True)

# --- ENGINE MANAGER ---
def is_engine_running() -> bool:
    """
    Sprawdza czy silnik main.py jest żywy i aktywny.
    Dwuetapowa weryfikacja:
    1. PID istnieje w systemie (proces żyje)
    2. Heartbeat jest świeży < 60s (silnik nie jest zawieszony)
    """
    if not os.path.exists(PID_FILE):
        return False

    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # Wysyła sygnał 0 — sprawdza czy PID istnieje
    except (OSError, ValueError):
        # Stale PID — silnik crashował, sprzątamy
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
        try:
            if os.path.exists(HEARTBEAT_FILE):
                os.remove(HEARTBEAT_FILE)
        except Exception:
            pass
        return False

    # PID żyje. Sprawdź heartbeat.
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, 'r') as f:
                ts = float(f.read().strip())
            age = time.time() - ts
            if age > _HEARTBEAT_TIMEOUT:
                # Silnik zawieszony — PID żyje, ale pętla główna nie bije
                return False
            return True
        except (OSError, ValueError):
            pass

    # Brak heartbeatu = silnik jeszcze startuje (pierwsze sekundy: backup + sync)
    # Grace period oparty o wiek PID file
    try:
        pid_age = time.time() - os.path.getmtime(PID_FILE)
        return pid_age < _ENGINE_START_GRACE
    except Exception:
        return True


def start_engine():
    """Uruchamia main.py jako proces tła."""
    if is_engine_running():
        return

    # Wyczyść stare pliki sterujące (heartbeat, PID) i CRITICAL STOP flag
    for f in (PID_FILE, HEARTBEAT_FILE):
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass
    # Usuń flagę krytycznego stopu przy restarcie operatora
    try:
        from app import critical_monitor
        critical_monitor.clear_stop()
    except Exception:
        pass

    # Truncate log
    try:
        open(LOG_FILE, 'w').close()
    except Exception:
        pass

    log_handle = open(LOG_FILE, "a")
    process = subprocess.Popen(
        [sys.executable, "-u", "main.py"],
        cwd=ROOT_DIR,
        stdout=log_handle,
        stderr=log_handle,
    )
    # Zapisz PID od razu po Popen
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
    except Exception as e:
        print(f"Błąd zapisu PID: {e}")


def stop_engine():
    """Zatrzymuje silnik (SIGTERM) i sprząta pliki sterujące."""
    pid = None
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            print(f"Błąd zatrzymywania silnika: {e}")
        finally:
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

    # Usuń heartbeat — GUI natychmiast widzi OFFLINE
    try:
        if os.path.exists(HEARTBEAT_FILE):
            os.remove(HEARTBEAT_FILE)
    except Exception:
        pass

def get_engine_logs(lines=200):
    """Czyta logi, odwraca kolejność (najnowsze na górze)."""
    if not os.path.exists(LOG_FILE): return "Brak logów. Uruchom silnik."
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            recent = all_lines[-lines:]
            recent.reverse() 
            return "".join(recent)
    except: return "Błąd odczytu."

def get_db():
    return Session(engine)

def save_uploaded_file(uploaded_file):
    if uploaded_file is not None:
        file_path = os.path.join(FILES_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return uploaded_file.name
    return None

try:
    # Świeża sesja per-render — SQLAlchemy nie cache'uje starych wyników
    session = get_db()

    # --- Upewnij się że tabele istnieją (jednorazowo per sesja Streamlit) ---
    if "db_initialized" not in st.session_state:
        from init_db import init_db
        init_db()
        st.session_state.db_initialized = True

    # --- AUTO-SYNC — max co 60 sekund, nie przy każdym rerenderze ---
    from app.brief_sync import sync_briefs_to_clients
    _now_ts = time.time()
    _last_sync = st.session_state.get("last_sync_ts", 0)
    if (_now_ts - _last_sync) >= 60:
        _auto_sync = sync_briefs_to_clients(session)
        st.session_state.last_sync_ts = _now_ts
        _sync_created = _auto_sync.get("created", 0)
        _sync_updated = _auto_sync.get("updated", 0)
        _sync_deactivated = _auto_sync.get("deactivated", 0)
        if _sync_created or _sync_updated or _sync_deactivated:
            _parts = []
            if _sync_created: _parts.append(f"{_sync_created} nowych")
            if _sync_updated: _parts.append(f"{_sync_updated} zaktualizowanych")
            if _sync_deactivated: _parts.append(f"{_sync_deactivated} dezaktywowanych")
            st.toast(f"Brief Sync: {', '.join(_parts)}", icon="🔄")

    # ==============================================================================
    # SIDEBAR: CENTRUM DOWODZENIA
    # ==============================================================================
    with st.sidebar:
        st.image("https://nexusagent.pl/logo.webp", width=150)

        # --- SEKCJA: SYSTEM ENGINE ---
        st.markdown("### 🖥️ SILNIK SYSTEMU")
        engine_status = is_engine_running()

        if engine_status:
            st.markdown('<div class="engine-status-box status-online">🟢 ONLINE</div>', unsafe_allow_html=True)
            if st.button("ZATRZYMAJ", width='stretch'):
                stop_engine()
                time.sleep(1)
                st.rerun()
        else:
            # Sprawdź czy silnik zatrzymał się z powodu awarii API
            try:
                from app import critical_monitor as _cm
                _stopped, _stop_reason = _cm.is_stopped()
            except Exception:
                _stopped, _stop_reason = False, ""

            if _stopped:
                st.markdown('<div class="engine-status-box status-offline">🚨 ZATRZYMANY — AWARIA API</div>', unsafe_allow_html=True)
                st.error(f"**Krytyczna awaria:** {_stop_reason}")
                st.info("Rozwiąż problem z API, a następnie kliknij URUCHOM — flaga zostanie automatycznie wyczyszczona.")
            else:
                st.markdown('<div class="engine-status-box status-offline">🔴 OFFLINE</div>', unsafe_allow_html=True)

            if st.button("URUCHOM", width='stretch'):
                start_engine()
                time.sleep(1)
                st.rerun()

        st.markdown("---")

        # --- SYNC Z PAYLOAD (ręczny trigger) ---
        st.markdown("### 🔄 Synchronizacja")
        if st.button("Wymuś Sync Briefów", width='stretch', help="Ręcznie pobiera zmiany z nexusagent.pl"):
            try:
                result = sync_briefs_to_clients(session)
                c, u, d = result.get("created", 0), result.get("updated", 0), result.get("deactivated", 0)
                if c or u or d:
                    parts = []
                    if c: parts.append(f"{c} nowych")
                    if u: parts.append(f"{u} zmian")
                    if d: parts.append(f"{d} dezaktywowanych")
                    st.success(f"Sync: {', '.join(parts)}")
                else:
                    st.info("Brak zmian w briefach.")
                st.rerun()
            except Exception as _sync_err:
                st.error(f"Błąd sync: {_sync_err}")

        st.markdown("---")

        # --- WYBÓR KLIENTA ---
        all_clients = session.query(Client).all()
        client_names = [c.name for c in all_clients]
        client_names.insert(0, "➕ DODAJ FIRMĘ")

        # Zapamiętaj wybranego klienta w session_state — st.rerun() nie resetuje wyboru
        if "selected_client" not in st.session_state:
            st.session_state.selected_client = client_names[1] if len(all_clients) > 0 else client_names[0]
        if st.session_state.selected_client not in client_names:
            st.session_state.selected_client = client_names[1] if len(all_clients) > 0 else client_names[0]

        _default_idx = client_names.index(st.session_state.selected_client)
        selected_option = st.radio("WYBIERZ AGENTA:", client_names, index=_default_idx, key="client_radio")
        st.session_state.selected_client = selected_option

        client = None
        if selected_option != "➕ DODAJ FIRMĘ":
            client = session.query(Client).filter(Client.name == selected_option).first()
            st.markdown("---")
            
            if client:
                status_color = "🟢" if client.status == "ACTIVE" else "🔴"
                # Wyświetlamy tryb w Sidebarze
                mode_icon = "💼" if client.mode == "JOB_HUNT" else "💰"
                st.markdown(f"### {mode_icon} {client.status}")
                st.caption(f"Tryb: {client.mode}") 
                
                # Wyświetlamy metodę wysyłki w sidebarze
                send_icon = "🚀" if getattr(client, 'sending_mode', 'DRAFT') == "AUTO" else "📝"
                st.caption(f"Wysyłka: {getattr(client, 'sending_mode', 'DRAFT')} {send_icon}")

                c1, c2 = st.columns(2)
                if client.status == "ACTIVE":
                    if c1.button("PAUZA"):
                        client.status = "PAUSED"
                        session.commit()
                        st.rerun()
                else:
                    if c1.button("START"):
                        client.status = "ACTIVE"
                        session.commit()
                        st.rerun()

    # ==============================================================================
    # VIEW: ONBOARDING
    # ==============================================================================
    if selected_option == "➕ DODAJ FIRMĘ":
        st.title("📝 Onboarding Nowej Firmy")
        with st.form("new_client_form"):
            c1, c2, c3 = st.columns(3)
            with c1: name = st.text_input("Nazwa Firmy (ID)")
            with c2: industry = st.text_input("Branża")
            with c3: sender = st.text_input("Nadawca")
            
            c_uvp, c_icp = st.columns(2)
            with c_uvp: uvp = st.text_area("Value Proposition")
            with c_icp: icp = st.text_area("Ideal Customer Profile")
            
            mode_sel = st.selectbox("Tryb Agenta", ["SALES", "JOB_HUNT"], index=0)

            t1, t2, t3 = st.columns(3)
            with t1: smtp_host = st.text_input("SMTP Host", "smtp.gmail.com")
            with t2: smtp_port = st.number_input("SMTP Port", 465)
            with t3: smtp_user = st.text_input("Email User")
            
            pass_input = st.text_input("Hasło", type="password")
            
            st.markdown("#### 🎨 Branding")
            html_foot = st.text_area("Stopka HTML")

            st.markdown("#### ⚖️ RODO / Compliance")
            st.caption("URL Polityki Prywatności klienta — doklejany do klauzuli RODO w każdym mailu. Link wypisania jest generowany automatycznie (nexusagent.pl/optout).")
            onb_privacy_url = st.text_input("URL Polityki Prywatności", placeholder="https://twoja-firma.pl/polityka-prywatnosci")

            if st.form_submit_button("🚀 Utwórz", type="primary"):
                if not name:
                    st.error("Nazwa wymagana")
                else:
                    encrypted_pass = encrypt_credential(pass_input) if pass_input else ""
                    nc = Client(
                        name=name, industry=industry, sender_name=sender,
                        value_proposition=uvp, ideal_customer_profile=icp,
                        mode=mode_sel,
                        sending_mode="DRAFT",
                        smtp_server=smtp_host, smtp_port=smtp_port, smtp_user=smtp_user,
                        smtp_password=encrypted_pass, html_footer=html_foot, status="ACTIVE",
                        privacy_policy_url=onb_privacy_url or None,
                    )
                    session.add(nc)
                    session.commit()
                    st.success("Zapisano.")
                    time.sleep(1)
                    st.rerun()

    # ==============================================================================
    # VIEW: DASHBOARD KLIENTA
    # ==============================================================================
    elif client:
        col_head, col_live = st.columns([0.8, 0.2])
        with col_head:
            st.title(f"{client.name}")
            mode_desc = "Sprzedaż B2B" if client.mode == "SALES" else "Poszukiwanie Pracy"
            st.markdown(f"**Branża:** {client.industry} | **Nadawca:** {client.sender_name} | **Cel:** {mode_desc}")
        with col_live:
            st.write("")
            st.write("")
            live_mode = st.toggle("📡 TRYB LIVE", value=False, help="Płynne odświeżanie danych")

        # 1. PLACEHOLDERY DLA DANYCH DYNAMICZNYCH
        metrics_placeholder = st.empty()

        st.markdown("---")
        log_label = "📜 PODGLĄD ZDARZEŃ SILNIKA"
        if live_mode: log_label += " <span class='live-dot'>● REC</span>"

        with st.expander(log_label, expanded=True):
            if not live_mode:
                if st.button("🔄 Odśwież Logi", key="refresh_logs_main"):
                    st.rerun()
            logs_placeholder = st.empty()

        # Placeholder w sidebarze — nadpisywany zamiast dokładać nowe elementy
        sidebar_phase2_placeholder = st.sidebar.empty()

        # FUNKCJA AKTUALIZUJĄCA DANE
        def update_dashboard_data():
            with Session(engine) as tmp_session:
                # Pobieramy świeże dane klienta (dla warmupa)
                fresh_client = tmp_session.query(Client).filter(Client.id == client.id).first()

                c_new = tmp_session.query(Lead).join(Campaign).filter(Campaign.client_id == client.id, Lead.status == "NEW").count()
                c_ready = tmp_session.query(Lead).join(Campaign).filter(Campaign.client_id == client.id, Lead.status == "ANALYZED").count()
                c_draft = tmp_session.query(Lead).join(Campaign).filter(Campaign.client_id == client.id, Lead.status == "DRAFTED").count()

                today = datetime.now().date()
                sent_today = tmp_session.query(Lead).join(Campaign).filter(
                    Campaign.client_id == client.id,
                    Lead.status == "SENT",
                    func.date(Lead.sent_at) == today
                ).count()

                # --- WARMUP CALC ---
                eff_limit = 50
                is_warmup = False
                if fresh_client:
                    eff_limit = calculate_daily_limit(fresh_client)
                    target = fresh_client.daily_limit or 50
                    is_warmup = fresh_client.warmup_enabled and eff_limit < target

                limit_display = f"{sent_today}/{eff_limit}"
                if is_warmup: limit_display += " 🔥"

                with metrics_placeholder.container():
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("W kolejce (New)", c_new)
                    k2.metric("Do napisania", c_ready)
                    k3.metric("Do wysłania", c_draft)
                    k4.metric("Dziś wysłano", limit_display, delta=eff_limit-sent_today, delta_color="normal")

            logs = get_engine_logs(200)
            logs_placeholder.markdown(f'<div class="console-logs">{logs}</div>', unsafe_allow_html=True)

            # PHASE 2 HEALTH CHECK
            if PHASE2_ENABLED:
                try:
                    from app.redis_client import redis_client
                    redis_ok = redis_client.ping()
                    
                    if redis_ok:
                        sidebar_phase2_placeholder.success("⚡ Phase 2: ACTIVE")
                    else:
                        sidebar_phase2_placeholder.error("⚠️ Redis: DISCONNECTED")
                except:
                    sidebar_phase2_placeholder.warning("⚠️ Phase 2: DISABLED")

        # PANEL AKCJI RĘCZNYCH
        st.markdown("### 🛠️ Sterowanie Manualne")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        
        with col_m1:
            if st.button("1. Szukaj (Scout)", type="primary"):
                camp = session.query(Campaign).filter(Campaign.client_id == client.id, Campaign.status == "ACTIVE").first()
                if camp:
                    strategy = generate_strategy(client, camp.strategy_prompt, camp.id)
                    if strategy and strategy.search_queries:
                        asyncio.run(run_scout_async(session, camp.id, strategy))
                        st.success("Scout zakończył.")
        
        with col_m2:
            if st.button(f"2. Analizuj", type="primary"):
                with st.status("Analiza..."):
                    leads = session.query(Lead).join(Campaign).filter(Campaign.client_id == client.id, Lead.status == "NEW").limit(5).all()
                    for l in leads: analyze_lead(session, l.id)
                    st.success("Gotowe.")

        with col_m3:
            if st.button(f"3. Pisz Maile", type="primary"):
                with st.status("Pisanie..."):
                    leads = session.query(Lead).join(Campaign).filter(Campaign.client_id == client.id, Lead.status == "ANALYZED").limit(5).all()
                    for l in leads: generate_email(session, l.id)
                    st.success("Gotowe.")

        with col_m4:
            if st.button(f"4. Wyślij", type="primary"):
                # DNS VALIDATOR (Wektor 4 antyspam)
                from app.tools import verify_sender_dns
                if client.smtp_user and "@" in client.smtp_user:
                    domain = client.smtp_user.split("@")[1]
                    dns_status = verify_sender_dns(domain)
                    if not dns_status.get("spf_ok") or not dns_status.get("dmarc_ok"):
                        st.error(f"🛑 [BLOKADA ANTYSZAM] Domena '{domain}' nie ma poprawnego rekordu SPF lub DMARC! Wysyłka zablokowana do czasu poprawy DNS.")
                        st.stop()
                        
                with st.status("Wysyłka..."):
                    process_followups(session, client)
                    leads = session.query(Lead).join(Campaign).filter(Campaign.client_id == client.id, Lead.status == "DRAFTED").limit(5).all()
                    for l in leads: 
                        save_draft_via_imap(l, client)
                        l.status = "SENT"
                        l.sent_at = func.now()
                        session.commit()
                    st.success("Wysłano.")

        st.markdown("---")
        # ZAKŁADKI
        tab_conf, tab_camp, tab_rep, tab_data, tab_phase2 = st.tabs(["⚙️ KONFIGURACJA", "🚀 KAMPANIE", "📊 RAPORTY", "📂 BAZA DANYCH", "⚡ PHASE 2"])

        # --- TAB 1: PEŁNA KONFIGURACJA ---
        with tab_conf:
            st.markdown("#### 🏛️ Generator Stopki B2B (API gov.pl - KSH)")
            st.caption("Wpisz NIP lub KRS i uzupełnij dane kontaktowe. System pobierze pozostałe dane z rejestrów państwowych i wygeneruje pełną stopkę prawną.")
            
            krs_row1, krs_row2 = st.columns(2)
            with krs_row1:
                krs_nip = st.text_input("🏦 NIP lub KRS", value=getattr(client, 'nip', '') or "", key=f"nip_{client.id}", placeholder="np. 7123498515 lub 0000780210")
            with krs_row2:
                krs_website = st.text_input("🌐 Strona internetowa", value="", key=f"web_{client.id}", placeholder="np. nexusagent.pl")
                
            krs_row3, krs_row4 = st.columns(2)
            with krs_row3:
                krs_phone = st.text_input("📞 Numer telefonu", value="", key=f"phone_{client.id}", placeholder="np. +48 535 604 904")
            with krs_row4:
                krs_email = st.text_input("📧 Adres email kontaktowy", value=client.smtp_user or "", key=f"email_{client.id}", placeholder="np. kontakt@firma.pl")

            if st.button("⬇️ Pobierz dane z gov.pl i wygeneruj stopkę", type="primary"):
                if not krs_nip:
                    st.error("Wpisz NIP lub KRS!")
                elif not krs_phone or not krs_email or not krs_website:
                    st.warning("⚠️ Uzupełnij telefon, email i stronę www — to wymagane elementy profesjonalnej stopki.")
                else:
                    with st.spinner("Odpytuję Ministerstwo Finansów i MS KRS..."):
                        from app.krs_api import generate_full_legal_footer
                        res = generate_full_legal_footer(krs_nip)
                        if res.get("success"):
                            c = session.query(Client).get(client.id)
                            c.nip = krs_nip
                            
                            # Nazwa projektu = client.name, Nazwa prawna = z KRS
                            brand_name = c.name
                            legal_name = res.get('name') or c.name
                            c.legal_name = legal_name  # Zapisz nazwę prawną z KRS (ADO w RODO)
                            
                            # BUDOWANIE STOPKI WEDŁUG WZORU (SUCHA FORMA REJESTROWA - ZERO REKLAMY)
                            footer_html = f"""<br/><br/>
<table style="font-family: Arial, sans-serif; font-size: 13px; color: #333; border-collapse: collapse;">
  <tr>
    <td style="padding-right: 15px; border-right: 2px solid #0066cc;">
      <strong style="color: #0066cc; font-size: 14px;">{brand_name}</strong><br/>
      {legal_name}
    </td>
    <td style="padding-left: 15px;">
      📞 <a href="tel:{krs_phone.replace(' ', '')}" style="color: #333; text-decoration: none;">{krs_phone}</a><br/>
      📧 <a href="mailto:{krs_email}" style="color: #0066cc;">{krs_email}</a><br/>
      🌐 <a href="https://{krs_website.replace('https://', '').replace('http://', '')}" style="color: #0066cc;">{krs_website.replace('https://', '').replace('http://', '')}</a>
    </td>
  </tr>
  <tr>
    <td colspan="2" style="padding-top: 10px; font-size: 10px; color: #666; line-height: 1.3;">
      {res.get('address') or 'Brak adresu'}<br/>
      {res.get('sad_rejonowy')}<br/>
      KRS: {res.get('krs') or krs_nip} | NIP: {res.get('nip') or krs_nip} | REGON: {res.get('regon') or '...'}<br/>
      Kapitał zakładowy: {res.get('kapital_zakladowy')} PLN
    </td>
  </tr>
</table>"""
                            c.html_footer = footer_html
                            session.commit()
                            st.success("✅ Stopka prawna wygenerowana i zapisana! Odśwież stronę (Ctrl+R) aby zobaczyć zmiany w podglądzie.")
                        else:
                            st.error(res.get("error_message"))

            st.markdown("---")
            st.markdown("#### Edycja DNA i Ustawień")
            with st.form("edit_client_full"):
                c1, c2, c3 = st.columns(3)
                with c1: e_name = st.text_input("Nazwa Firmy", client.name)
                with c2: e_ind = st.text_input("Branża", client.industry)
                with c3: e_sender = st.text_input("Nadawca", client.sender_name)

                # --- PRZEŁĄCZNIKI (MODE & SENDING) ---
                c_mode1, c_mode2 = st.columns(2)
                
                with c_mode1:
                    # Tryb Strategiczny
                    curr_mode_index = 0 if client.mode == "SALES" else 1
                    e_mode = st.radio("Cel Agenta:", ["SALES", "JOB_HUNT"], index=curr_mode_index, horizontal=True)
                
                with c_mode2:
                    # Tryb Techniczny (Wysyłka)
                    # Używamy getattr na wypadek gdyby w bazie jeszcze nie było wartości (dla starych klientów)
                    curr_send = getattr(client, 'sending_mode', 'DRAFT')
                    send_idx = 0 if curr_send == "DRAFT" else 1
                    e_send = st.radio("Metoda Wysyłki:", ["DRAFT", "AUTO"], index=send_idx, horizontal=True)
                    
                    if e_send == "AUTO":
                        st.warning("⚠️ AUTO wysyła maile natychmiast! Upewnij się, że Warm-up działa.")
                # -------------------------------------

                ec_uvp, ec_icp = st.columns(2)
                with ec_uvp: e_uvp = st.text_area("Value Proposition / Twoje BIO", client.value_proposition, height=120)
                with ec_icp: e_icp = st.text_area("Ideal Customer / Pracodawca", client.ideal_customer_profile, height=120)

                ec_tone, ec_neg = st.columns(2)
                with ec_tone: e_tone = st.text_input("Tone of Voice", client.tone_of_voice)
                with ec_neg: e_neg = st.text_area("Negative Constraints", client.negative_constraints, height=70)
                e_cases = st.text_area("Case Studies / Projekty", client.case_studies, height=100)

                et1, et2, et3 = st.columns(3)
                with et1:
                    e_host = st.text_input("SMTP Host", client.smtp_server)
                    e_imap = st.text_input("IMAP Host", client.imap_server)
                with et2:
                    e_port = st.number_input("SMTP Port", value=client.smtp_port or 465)
                    e_iport = st.number_input("IMAP Port", value=client.imap_port or 993)
                with et3:
                    e_user = st.text_input("SMTP User", client.smtp_user)
                    e_pass = st.text_input("Hasło Aplikacji", value=client.smtp_password or "", type="password")
                    if client.smtp_password and not is_encrypted(client.smtp_password):
                        st.caption("⚠️ Hasło niezaszyfrowane — zapisz ponownie")
                
                e_limit = st.number_input("Limit Dzienny (Docelowy)", value=client.daily_limit or 50)
                curr_file = client.attachment_filename or "Brak pliku"
                st.info(f"Obecny załącznik: {curr_file}")
                e_file = st.file_uploader("Zmień załącznik", type=['pdf', 'docx'])

                # --- SEKCJA WARM-UP ---
                st.markdown("---")
                st.markdown("#### 🔥 Strategia Rozgrzewki (Warm-up)")
                
                c_warm1, c_warm2 = st.columns([0.2, 0.8])
                with c_warm1:
                    e_warm_enable = st.checkbox("Włącz Warm-up", value=client.warmup_enabled)
                with c_warm2:
                    if e_warm_enable:
                        st.info(f"Start: {client.warmup_started_at.strftime('%Y-%m-%d') if client.warmup_started_at else 'Dziś'}")

                wc1, wc2 = st.columns(2)
                with wc1:
                    e_warm_start = st.number_input("Start (ile maili 1. dnia)", value=client.warmup_start_limit or 2, disabled=not e_warm_enable)
                with wc2:
                    e_warm_inc = st.number_input("Przyrost (ile więcej co dzień)", value=client.warmup_increment or 2, disabled=not e_warm_enable)

                if e_warm_enable:
                    final_lim = e_limit
                    days_to_max = max(0, int((final_lim - e_warm_start) / e_warm_inc))
                    st.caption(f"📈 Pełną moc ({final_lim}/dzień) osiągniesz za ok. {days_to_max} dni.")
                # ----------------------

                st.markdown("---")

                # --- SEKCJA: MODELE AI ---
                st.markdown("#### 🧠 Modele AI (per Agent)")
                st.caption("Wybierz model AI osobno dla każdej roli agenta. Modele bez skonfigurowanego klucza API są zablokowane (🔒).")

                if MODEL_FACTORY_OK:
                    api_keys = get_available_api_keys()

                    def _model_options(role: str):
                        """Zwraca (labels_list, label_to_id_map, current_label) dla selectbox."""
                        models = get_available_models(role)
                        labels = []
                        label_to_id = {}
                        current_attr = f"{role}_model"
                        current_val = getattr(client, current_attr, None) or DEFAULT_MODEL
                        current_label = None

                        for m in models:
                            mid = m["model_id"]
                            desc = m["description"]
                            available = m["available"]

                            if available:
                                label = f"{mid}  —  {desc}"
                            else:
                                label = f"🔒 {mid}  —  {desc}"

                            labels.append(label)
                            label_to_id[label] = mid

                            if mid == current_val:
                                current_label = label

                        # Fallback: jeśli current_val nie pasuje do żadnego modelu
                        if current_label is None and labels:
                            current_label = labels[0]

                        return labels, label_to_id, current_label

                    mc1, mc2, mc3 = st.columns(3)

                    with mc1:
                        st.markdown("**🕵️ Scout + Strategy**")
                        s_labels, s_map, s_current = _model_options("scout")
                        _key_s = f"sel_scout_{client.id}"
                        if _key_s not in st.session_state:
                            st.session_state[_key_s] = s_current
                        e_scout_label = st.selectbox(
                            "Model Scouta",
                            options=s_labels,
                            key=_key_s,
                        )
                        e_scout_model = s_map.get(e_scout_label, DEFAULT_MODEL)

                    with mc2:
                        st.markdown("**🔬 Researcher**")
                        r_labels, r_map, r_current = _model_options("researcher")
                        _key_r = f"sel_researcher_{client.id}"
                        if _key_r not in st.session_state:
                            st.session_state[_key_r] = r_current
                        e_researcher_label = st.selectbox(
                            "Model Researchera",
                            options=r_labels,
                            key=_key_r,
                        )
                        e_researcher_model = r_map.get(e_researcher_label, DEFAULT_MODEL)

                    with mc3:
                        st.markdown("**✍️ Writer + Auditor**")
                        w_labels, w_map, w_current = _model_options("writer")
                        _key_w = f"sel_writer_{client.id}"
                        if _key_w not in st.session_state:
                            st.session_state[_key_w] = w_current
                        e_writer_label = st.selectbox(
                            "Model Writera",
                            options=w_labels,
                            key=_key_w,
                        )
                        e_writer_model = w_map.get(e_writer_label, DEFAULT_MODEL)

                    # Status kluczy API
                    key_status = []
                    if api_keys.get("gemini"): key_status.append("🔵 Gemini ✅")
                    else: key_status.append("🔵 Gemini ❌")
                    if api_keys.get("anthropic"): key_status.append("🟣 Claude ✅")
                    else: key_status.append("🟣 Claude ❌ (dodaj ANTHROPIC_API_KEY)")
                    if api_keys.get("deepseek"): key_status.append("🟢 DeepSeek ✅")
                    else: key_status.append("🟢 DeepSeek ❌ (dodaj DEEPSEEK_API_KEY)")
                    st.caption("Klucze API: " + " | ".join(key_status))
                else:
                    st.warning("⚠️ Moduł model_factory niedostępny — modele AI niezmienione.")
                    e_scout_model = getattr(client, "scout_model", None) or DEFAULT_MODEL
                    e_researcher_model = getattr(client, "researcher_model", None) or DEFAULT_MODEL
                    e_writer_model = getattr(client, "writer_model", None) or DEFAULT_MODEL

                st.markdown("---")
                st.markdown("#### ⚖️ RODO / Compliance")
                st.caption("Klauzula RODO jest automatycznie doklejana na dole każdego wysyłanego maila. Uzupełnij poniższe linki.")

                curr_privacy = getattr(client, "privacy_policy_url", None) or ""

                rc1, rc2 = st.columns(2)
                with rc1:
                    e_privacy_url = st.text_input(
                        "URL Polityki Prywatności",
                        value=curr_privacy,
                        placeholder="https://twoja-firma.pl/polityka-prywatnosci",
                    )
                with rc2:
                    st.info("🔗 Link wypisania generowany automatycznie\n(nexusagent.pl/optout?t=...)", icon=None)

                if not curr_privacy:
                    st.warning(
                        "⚠️ Brak URL Polityki Prywatności. Uzupełnij przed wysyłką produkcyjną."
                    )

                st.markdown("---")
                st.markdown("#### Stopka HTML (Branding / Podpis)")
                e_footer = st.text_area("Kod HTML", value=client.html_footer, height=200)

                if st.form_submit_button("💾 Zapisz Zmiany", type="primary"):
                    client.name = e_name
                    client.industry = e_ind
                    client.sender_name = e_sender
                    client.mode = e_mode
                    client.sending_mode = e_send
                    client.value_proposition = e_uvp
                    client.ideal_customer_profile = e_icp
                    client.tone_of_voice = e_tone
                    client.negative_constraints = e_neg
                    client.case_studies = e_cases
                    client.smtp_server = e_host
                    client.imap_server = e_imap
                    client.smtp_port = e_port
                    client.imap_port = e_iport
                    client.smtp_user = e_user
                    if e_pass:
                        client.smtp_password = encrypt_credential(e_pass)
                    client.daily_limit = e_limit
                    client.html_footer = e_footer
                    client.privacy_policy_url = e_privacy_url or None
                    client.scout_model = e_scout_model
                    client.researcher_model = e_researcher_model
                    client.writer_model = e_writer_model

                    if e_file:
                        fname = save_uploaded_file(e_file)
                        client.attachment_filename = fname

                    # LOGIKA ZAPISU WARM-UP
                    if e_warm_enable and not client.warmup_enabled:
                        client.warmup_started_at = datetime.now()
                    client.warmup_enabled = e_warm_enable
                    client.warmup_start_limit = e_warm_start
                    client.warmup_increment = e_warm_inc

                    session.commit()
                    st.success("Zapisano!")
                    st.rerun()

        # --- TAB 2: KAMPANIE ---
        with tab_camp:
            st.markdown("#### Cele Zwiadowcze")
            if client.mode == "JOB_HUNT":
                st.info("💡 W trybie JOB_HUNT wpisz np.: 'Software House Python Kraków', 'AI Startups Remote'.")
            else:
                st.info("💡 W trybie SALES wpisz np.: 'Sklepy meblowe Warszawa', 'Biura księgowe'.")

            with st.form("new_camp"):
                target = st.text_area("Cel")
                if st.form_submit_button("Dodaj Cel"):
                    nc = Campaign(client_id=client.id, name="Auto", status="ACTIVE", strategy_prompt=target)
                    session.add(nc)
                    session.commit()
                    st.success("Dodano")
                    st.rerun()
            active = session.query(Campaign).filter(Campaign.client_id == client.id, Campaign.status == "ACTIVE").order_by(Campaign.id.desc()).all()
            
            # --- SEKCJA KASOWANIA CELÓW (TAB 2) ---
            st.markdown("---")
            if not active:
                st.caption("Brak aktywnych celów.")
                
            for c in active:
                col_text, col_btn = st.columns([0.85, 0.15])
                with col_text:
                    st.code(c.strategy_prompt, language="text")
                with col_btn:
                    if st.button("🗑️ Usuń", key=f"del_camp_{c.id}", width='stretch'):
                        c.status = "ARCHIVED" # Soft delete
                        session.commit()
                        st.success("Usunięto.")
                        time.sleep(0.5)
                        st.rerun()
            # -------------------------------------

        # --- TAB 3: RAPORTOWANIE ---
        with tab_rep:
            st.markdown("#### 📄 Centrum Raportowania Enterprise")
            c_rep1, c_rep2, c_rep3 = st.columns(3)
            with c_rep1: d_start = st.date_input("Od dnia", value=datetime.now() - timedelta(days=30))
            with c_rep2: d_end = st.date_input("Do dnia", value=datetime.now())
            with c_rep3:
                st.write("") 
                st.write("") 
                gen_btn = st.button("🖨️ Wygeneruj PDF", type="primary", width='stretch')

            if gen_btn:
                with st.spinner("Generowanie..."):
                    try:
                        pdf_path = create_pdf_report(session, client.id)
                        if pdf_path and os.path.exists(pdf_path):
                            st.success(f"Gotowe!")
                            with open(pdf_path, "rb") as pdf_file:
                                st.download_button("📥 POBIERZ", pdf_file, file_name=os.path.basename(pdf_path), mime="application/pdf", width='stretch')
                    except Exception as e: st.error(f"Błąd: {e}")

        # --- TAB 4: DANE ---
        with tab_data:
            st.markdown("#### Surowe Dane Leadów")
            try:
                q = session.query(Lead.id, GlobalCompany.name, Lead.status, Lead.target_email).join(GlobalCompany).join(Campaign).filter(Campaign.client_id == client.id)
                df = pd.read_sql(q.statement, session.connection())
                st.dataframe(df, width='stretch')            
            except Exception as e: st.warning("Brak danych.")

        # --- TAB 5: PHASE 2 MONITORING ---
        with tab_phase2:
            st.markdown("### ⚡ Redis Performance Monitoring")
            
            # Import Phase 2 modules
            try:
                from app.cache_manager import cache_manager
                from app.rate_limiter import rate_limiter
                from app.queue_manager import queue_manager
                from app.tools import get_email_cache_stats
                PHASE2_AVAILABLE = True
            except ImportError:
                st.error("❌ Phase 2 modules not installed")
                PHASE2_AVAILABLE = False
            
            if PHASE2_AVAILABLE:
                # Refresh button
                col_refresh, col_auto = st.columns([0.3, 0.7])
                with col_refresh:
                    if st.button("🔄 Odśwież Stats", key="refresh_phase2"):
                        st.rerun()
                with col_auto:
                    auto_refresh = st.toggle("Auto-refresh (3s)", value=False)
                
                st.markdown("---")
                
                # ==========================================
                # SECTION 1: CACHE STATISTICS
                # ==========================================
                st.markdown("#### 💾 Cache Performance")
                
                try:
                    cache_stats = cache_manager.get_cache_stats()
                    email_stats = get_email_cache_stats()
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric(
                            "Emails Cached",
                            email_stats.get("total_cached", 0),
                            help="Liczba zweryfikowanych emaili w cache"
                        )
                    
                    with col2:
                        st.metric(
                            "Companies Cached",
                            cache_stats.get("companies_cached", 0),
                            help="Liczba zescrapowanych firm w cache"
                        )
                    
                    with col3:
                        st.metric(
                            "Campaigns Tracked",
                            cache_stats.get("campaigns_tracked", 0),
                            help="Liczba kampanii z historią"
                        )
                    
                    with col4:
                        ttl_days = email_stats.get("ttl_avg_days", 0)
                        st.metric(
                            "Avg TTL",
                            f"{ttl_days} days",
                            help="Średni czas życia cache"
                        )
                    
                    # Cost savings calculator
                    st.markdown("---")
                    st.markdown("#### 💰 Cost Savings (Real-time)")
                    
                    emails_cached = email_stats.get("total_cached", 0)
                    companies_cached = cache_stats.get("companies_cached", 0)
                    
                    DEBOUNCE_COST = 0.25
                    FIRECRAWL_COST = 0.10
                    
                    email_savings = emails_cached * DEBOUNCE_COST
                    scraping_savings = companies_cached * FIRECRAWL_COST
                    total_savings = email_savings + scraping_savings
                    
                    col_s1, col_s2, col_s3 = st.columns(3)
                    
                    with col_s1:
                        st.metric(
                            "Email Verification Saved",
                            f"${email_savings:.2f}",
                            delta=f"{emails_cached} API calls avoided"
                        )
                    
                    with col_s2:
                        st.metric(
                            "Scraping Saved",
                            f"${scraping_savings:.2f}",
                            delta=f"{companies_cached} scrapes avoided"
                        )
                    
                    with col_s3:
                        st.metric(
                            "Total Savings",
                            f"${total_savings:.2f}",
                            delta="Since cache start",
                            delta_color="off"
                        )
                    
                    # Monthly projection
                    if emails_cached > 0 or companies_cached > 0:
                        st.info(f"📊 **Monthly Projection:** ${total_savings * 30:.2f}/month (assuming current rate)")
                    
                except Exception as e:
                    st.error(f"Cache stats error: {e}")
                
                st.markdown("---")
                
                # ==========================================
                # SECTION 2: RATE LIMITING
                # ==========================================
                st.markdown("#### 🚦 Rate Limiting Status")
                
                try:
                    rate_stats = rate_limiter.get_rate_limit_stats()
                    
                    col_r1, col_r2, col_r3 = st.columns(3)
                    
                    with col_r1:
                        global_emails = rate_stats.get("global_daily_emails", 0)
                        st.metric(
                            "Emails Sent Today (Global)",
                            global_emails,
                            help="Total emails sent across all clients"
                        )
                    
                    with col_r2:
                        usage_percent = rate_stats.get("sendgrid_usage_percent", 0)
                        color = "🟢" if usage_percent < 50 else "🟡" if usage_percent < 80 else "🔴"
                        st.metric(
                            f"SendGrid Usage {color}",
                            f"{usage_percent}%",
                            delta=f"{500 - global_emails} remaining",
                            delta_color="normal"
                        )
                    
                    with col_r3:
                        # Client-specific emails today
                        client_emails_today = rate_limiter.get_emails_sent_today(client.id)
                        client_limit = calculate_daily_limit(client)
                        st.metric(
                            "This Client Today",
                            f"{client_emails_today}/{client_limit}",
                            delta=f"{client_limit - client_emails_today} remaining"
                        )
                    
                    # API usage
                    st.markdown("##### API Usage (Last Minute)")
                    api_usage = rate_stats.get("api_usage_per_minute", {})
                    
                    col_a1, col_a2, col_a3 = st.columns(3)
                    
                    with col_a1:
                        db_count = api_usage.get("debounce", 0)
                        db_limit = 10
                        st.progress(db_count / db_limit if db_limit > 0 else 0)
                        st.caption(f"DeBounce: {db_count}/10 per min")
                    
                    with col_a2:
                        fc_count = api_usage.get("firecrawl", 0)
                        fc_limit = 5
                        st.progress(fc_count / fc_limit if fc_limit > 0 else 0)
                        st.caption(f"Firecrawl: {fc_count}/5 per min")
                    
                    with col_a3:
                        ap_count = api_usage.get("apify", 0)
                        ap_limit = 10
                        st.progress(ap_count / ap_limit if ap_limit > 0 else 0)
                        st.caption(f"Apify: {ap_count}/10 per min")
                    
                except Exception as e:
                    st.error(f"Rate limit stats error: {e}")
                
                st.markdown("---")
                
                # ==========================================
                # SECTION 3: QUEUE SYSTEM (if enabled)
                # ==========================================
                st.markdown("#### 📥 Queue System")
                
                try:
                    queue_stats = queue_manager.get_queue_stats()
                    
                    col_q1, col_q2, col_q3, col_q4 = st.columns(4)
                    
                    queues = queue_stats.get("queues", {})
                    
                    with col_q1:
                        st.metric("New Queue", queues.get("new", 0))
                    
                    with col_q2:
                        st.metric("Analyzed Queue", queues.get("analyzed", 0))
                    
                    with col_q3:
                        st.metric("Drafted Queue", queues.get("drafted", 0))
                    
                    with col_q4:
                        st.metric("Priority Queue", queues.get("priority", 0), delta="VIP")
                    
                    # Processing & Workers
                    col_w1, col_w2, col_w3 = st.columns(3)
                    
                    with col_w1:
                        st.metric(
                            "Currently Processing",
                            queue_stats.get("processing", 0),
                            help="Leads being processed right now"
                        )
                    
                    with col_w2:
                        st.metric(
                            "Active Workers",
                            queue_stats.get("active_workers", 0),
                            help="Workers with active heartbeat"
                        )
                    
                    with col_w3:
                        st.metric(
                            "Total Pending",
                            queue_stats.get("total_pending", 0),
                            help="All leads in all queues"
                        )
                    
                    # Worker details
                    if queue_stats.get("active_workers", 0) > 0:
                        st.markdown("##### 👷 Active Workers")
                        workers = queue_manager.get_active_workers()
                        
                        worker_data = []
                        for w in workers:
                            worker_data.append({
                                "Worker ID": w.get("worker_id", "Unknown"),
                                "Client ID": w.get("client_id", "-"),
                                "Task": w.get("task", "idle"),
                                "Last Seen": w.get("last_seen", "Unknown")[:19]  # Trim microseconds
                            })
                        
                        if worker_data:
                            df_workers = pd.DataFrame(worker_data)
                            st.dataframe(df_workers, width='stretch', hide_index=True)
                    
                except Exception as e:
                    st.error(f"Queue stats error: {e}")
                
                st.markdown("---")
                
                # ==========================================
                # SECTION 4: MANAGEMENT ACTIONS
                # ==========================================
                st.markdown("#### 🛠️ Cache Management")
                
                col_m1, col_m2, col_m3 = st.columns(3)
                
                with col_m1:
                    if st.button("🗑️ Clear Email Cache", width='stretch'):
                        # This would need implementation in cache_manager
                        st.warning("⚠️ Feature coming soon")
                
                with col_m2:
                    if st.button("🔄 Reset Rate Limits", width='stretch'):
                        try:
                            rate_limiter.reset_client_limits(client.id)
                            st.success("✅ Limits reset")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                
                with col_m3:
                    if st.button("📊 Export Stats", width='stretch'):
                        try:
                            stats_export = {
                                "timestamp": datetime.now().isoformat(),
                                "cache": cache_stats,
                                "rate_limits": rate_stats,
                                "queues": queue_stats
                            }
                            
                            import json
                            stats_json = json.dumps(stats_export, indent=2)
                            st.download_button(
                                "💾 Download JSON",
                                stats_json,
                                file_name=f"phase2_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                mime="application/json"
                            )
                        except Exception as e:
                            st.error(f"Export error: {e}")
                
                # Auto-refresh logic
                if auto_refresh:
                    time.sleep(3)
                    st.rerun()


        # =================================================================
        # 3. PĘTLA ODŚWIEŻANIA
        # =================================================================
        if live_mode:
            while True:
                update_dashboard_data()
                time.sleep(1)
        else:
            update_dashboard_data()

finally:
    session.close()