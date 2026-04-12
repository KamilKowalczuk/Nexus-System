import os
from datetime import datetime
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")


def _now_pl():
    return datetime.now(PL_TZ)
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float, Date, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv

# Ładowanie konfiguracji z .env
load_dotenv()

# Pobranie adresu bazy danych
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Błąd: Brak zmiennej DATABASE_URL w pliku .env")

# --- KONFIGURACJA SILNIKA (ENTERPRISE EDITION) ---
# Optymalizacja pod wysokie współbieżne obciążenie (1000 klientów / 20 workerów)
engine = create_engine(
    DATABASE_URL,
    pool_size=20,           # Tyle połączeń trzymamy stale otwartych (Matchuje MAX_CONCURRENT_AGENTS)
    max_overflow=10,        # Tyle możemy otworzyć "na chwilę" w szczycie (Burst)
    pool_timeout=30,        # Jak długo wątek czeka na wolne połączenie zanim rzuci błędem
    pool_recycle=1800,      # Reset połączenia co 30 min (zapobiega "SSL SYSCALL error: EOF detected")
    pool_pre_ping=True,     # ✅ Testuj połączenie przed użyciem — zapobiega "server closed the connection unexpectedly"
    connect_args={
        "application_name": "nexus_engine", # Tagowanie połączeń w logach Postgresa
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 1. CLIENT DNA (Mózg Strategiczny) ---
class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # STATUS AGENCJI (ACTIVE / PAUSED)
    status = Column(String, default="ACTIVE") 
    mode = Column(String, default="SALES") # Opcje: "SALES", "JOB_HUNT"
    
    name = Column(String, nullable=False, unique=True) # np. "Koordynuj Zdrowie" (nazwa projektu/marki)
    nip = Column(String, nullable=True) # NIP do integracji z API KRS/REGON (Wektor 5)
    legal_name = Column(String, nullable=True) # Pełna nazwa prawna z KRS (np. "Carewise Sp. z o.o.") — ADO w RODO
    
    # PAYLOAD CMS RELATION (twarde FK do tabel Payload)
    payload_order_id = Column(Integer, nullable=True)  # orders.id z Payload
    payload_brief_id = Column(Integer, nullable=True)  # briefs.id z Payload
    
    # STRATEGICZNE DNA
    industry = Column(String)              # "Software House"
    value_proposition = Column(Text)       # "Dozimy MVP w 3 miesiące"
    ideal_customer_profile = Column(Text)  # "Fintechy, Seed/Series A"
    tone_of_voice = Column(String)         # "Profesjonalny, Direct"
    
    # HARD CONSTRAINTS
    negative_constraints = Column(Text)    # "Nie wspominaj o WordPress"
    case_studies = Column(Text)            # "Zrobiliśmy projekt X dla firmy Y..."
    
    # KONFIGURACJA TECHNICZNA
    sender_name = Column(String)           # "Kamil Kowalczuk"
    smtp_user = Column(String)             # "kamil@agencja.pl"
    smtp_password = Column(String)         # Hasło aplikacji
    smtp_server = Column(String)           # "smtp.googlemail.com"
    smtp_port = Column(Integer, default=465)
    imap_server = Column(String)           # np. imap.gmail.com
    imap_port = Column(Integer, default=993)
    daily_limit = Column(Integer, default=50) # Bezpiecznik wysyłki
    html_footer = Column(String, nullable=True) # Kod HTML stopki

    # --- WARM-UP CONFIG ---
    warmup_enabled = Column(Boolean, default=False)       # Czy rozgrzewka włączona?
    warmup_start_limit = Column(Integer, default=2)       # Od ilu zaczynamy?
    warmup_increment = Column(Integer, default=2)         # O ile zwiększamy dziennie?
    warmup_started_at = Column(DateTime, nullable=True)   # Kiedy zaczęliśmy?

    sending_mode = Column(String, default="DRAFT")

    attachment_filename = Column(String, nullable=True)

    # --- RODO / COMPLIANCE CONFIG ---
    privacy_policy_url = Column(String, nullable=True)  # URL do polityki prywatności klienta
    opt_out_link = Column(String, nullable=True)         # URL do formularza wypisania (PKE)

    # --- LLM MODEL CONFIG (per-agent) ---
    scout_model = Column(String, default="gemini-3.1-flash-lite-preview")      # Scout + Strategy
    researcher_model = Column(String, default="gemini-3.1-flash-lite-preview") # Researcher
    writer_model = Column(String, default="gemini-3.1-flash-lite-preview")     # Writer + Auditor

    campaigns = relationship("Campaign", back_populates="client")

# --- 2. GLOBAL KNOWLEDGE GRAPH (Pamięć Świata) ---
class GlobalCompany(Base):
    __tablename__ = "global_companies"
    
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, unique=True, index=True) # Klucz unikalny: "google.com"
    name = Column(String)
    
    # 360 INTELLIGENCE (Z Firecrawl)
    industry = Column(String, nullable=True)          # Branża z Google Maps (categoryName)
    address = Column(String, nullable=True)           # Adres fizyczny firmy
    tech_stack = Column(JSONB, default=[])       # ["React", "AWS"]
    decision_makers = Column(JSONB, default=[])  # [{"name": "Jan", "role": "CTO"}]
    pain_points = Column(JSONB, default=[])      # ["Wolna strona", "Brak mobile"]
    hiring_status = Column(String)               # "Hiring" / "Layoffs"
    
    # KONTAKT
    phone_number = Column(String, nullable=True)  # Numer telefonu z Google Maps

    # VALIDATION LAYER
    is_active = Column(Boolean, default=True)
    has_mx_records = Column(Boolean, default=False) 
    last_scraped_at = Column(DateTime, default=_now_pl)
    quality_score = Column(Integer, default=0) # 0-100

    leads = relationship("Lead", back_populates="company")

# --- 3. KAMPANIE (Zlecenia) ---
class Campaign(Base):
    __tablename__ = "campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    name = Column(String)            # "Szukanie Fintechów UK"
    status = Column(String, default="ACTIVE") # ACTIVE, PAUSED, COMPLETED
    
    # STRATEGIA
    strategy_prompt = Column(Text)   # "Znajdź firmy, które niedawno dostały dofinansowanie"
    target_region = Column(String)   # "UK, London"

    client = relationship("Client", back_populates="campaigns")
    leads = relationship("Lead", back_populates="campaign")

# --- 4. LEADS (Konkretne Szanse Sprzedażowe) ---
class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    global_company_id = Column(Integer, ForeignKey("global_companies.id"))
    
    # WYNIKI AGENTÓW
    ai_analysis_summary = Column(Text) # "Pasuje do ICP bo..."
    generated_email_subject = Column(String)
    generated_email_body = Column(Text)
    
    # KONTAKT
    target_email = Column(String, nullable=True) 

    # HALLUCINATION KILLER & DRIP
    ai_confidence_score = Column(Integer) # 0-100
    status = Column(String, default="NEW") # NEW -> SCRAPED -> DRAFTED -> SENT
    
    # FOLLOW-UP MECHANISM
    step_number = Column(Integer, default=1) 
    last_action_at = Column(DateTime, default=_now_pl)

    scheduled_for = Column(DateTime) # Kiedy wysłać?
    sent_at = Column(DateTime)       # Kiedy wysłano?
    
    campaign = relationship("Campaign", back_populates="leads")
    company = relationship("GlobalCompany", back_populates="leads")

    # SEKCJA ODPOWIEDZI (INBOX)
    replied_at = Column(DateTime, nullable=True)
    reply_content = Column(String, nullable=True) # Treść maila od klienta
    reply_sentiment = Column(String, nullable=True) # POSITIVE, NEGATIVE, NEUTRAL
    reply_analysis = Column(String, nullable=True) # Krótka notatka AI

class OptOut(Base):
    """
    Globalna kryptograficzna czarna lista (SaaS Tenant Isolation).

    Przechowuje WYŁĄCZNIE SHA-256 hashe — zero plain-text.
    Zgodna z zasadą minimalizacji danych (art. 5 ust. 1 lit. c RODO).

    entry_type:
        'EMAIL'  — hash adresu e-mail (bramka przy wysyłce)
        'DOMAIN' — hash domeny firmy  (bramka przy scoutingu i researchu)
    """
    __tablename__ = "opt_outs"

    id = Column(Integer, primary_key=True, index=True)
    value_hash = Column(String(64), unique=True, index=True, nullable=False)  # SHA-256 hex
    entry_type = Column(String(10), nullable=False, default="EMAIL")          # EMAIL | DOMAIN
    added_at = Column(DateTime, default=_now_pl)


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(String, index=True) # np. "Software House Kraków"
    client_id = Column(Integer, ForeignKey("clients.id"))
    searched_at = Column(DateTime, default=_now_pl)
    results_found = Column(Integer, default=0)

class CampaignStatistics(Base):
    """
    Enterprise Statistics Engine — dzienne metryki kampanii.
    Jeden wiersz per client_id per date. Payload CMS joinuje tę tabelę z briefs
    przez clients.name = briefs.company_name.
    UPSERT (INSERT ON CONFLICT UPDATE) przez stats_manager.py.
    """
    __tablename__ = "campaign_statistics"
    __table_args__ = (
        UniqueConstraint("client_id", "date", name="uq_client_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    # --- SCOUTING ---
    domains_scanned = Column(Integer, default=0)
    domains_approved = Column(Integer, default=0)
    domains_rejected = Column(Integer, default=0)
    domains_blacklisted = Column(Integer, default=0)

    # --- RESEARCH ---
    leads_analyzed = Column(Integer, default=0)
    emails_found = Column(Integer, default=0)
    emails_verified = Column(Integer, default=0)
    emails_rejected_freemail = Column(Integer, default=0)

    # --- WRITING ---
    emails_drafted = Column(Integer, default=0)
    avg_confidence_score = Column(Float, default=0.0)

    # --- DELIVERY ---
    emails_sent = Column(Integer, default=0)
    followup_step_2_sent = Column(Integer, default=0)
    followup_step_3_sent = Column(Integer, default=0)
    bounces = Column(Integer, default=0)
    dns_blocks = Column(Integer, default=0)

    # --- ENGAGEMENT ---
    replies_total = Column(Integer, default=0)
    replies_positive = Column(Integer, default=0)
    replies_negative = Column(Integer, default=0)
    replies_neutral = Column(Integer, default=0)
    opt_outs = Column(Integer, default=0)

    # --- OBLICZONE ---
    reply_rate = Column(Float, default=0.0)
    positive_rate = Column(Float, default=0.0)
    avg_response_time_hours = Column(Float, nullable=True)

    client = relationship("Client")


# Funkcja pomocnicza do pobierania sesji
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()