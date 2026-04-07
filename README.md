# NEXUS ENGINE v3.1

**Autonomiczny system cold-email B2B oparty na agentach AI.**

Nexus Engine to wieloagentowy silnik, ktory samodzielnie wyszukuje firmy pasujace do profilu klienta, bada je, pisze spersonalizowane maile i wysyla je z zachowaniem ludzkiego rytmu. System jest zaprojektowany jako SaaS — obsluguje wielu klientow jednoczesnie, kazdy z wlasnym briefem, limitem i konfiguracją.

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Redis](https://img.shields.io/badge/Redis-7-red)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-orange)

---

## Jak to dziala

System sklada sie z 5 autonomicznych agentow AI, ktore dzialaja w petli:

```
STRATEGIA → SCOUT → RESEARCHER → WRITER → SENDER
                                               ↓
                                          INBOX MONITOR
                                          (analiza odpowiedzi)
```

### Agenty

| Agent | Zadanie | Technologia |
|-------|---------|-------------|
| **Strategy** | Generuje zapytania wyszukiwania na podstawie briefu klienta | Gemini / Claude |
| **Scout** | Wyszukuje firmy przez Google Maps, filtruje przez AI Gatekeeper | Apify + Gemini |
| **Researcher** | Scraping strony firmy, ekstrakcja danych kontaktowych, tech stacku, pain pointow | Firecrawl + Gemini |
| **Writer** | Pisze spersonalizowane maile cold-email + follow-upy | Gemini / Claude |
| **Sender** | Wysyla maile przez SMTP lub zapisuje drafty przez IMAP | smtplib / imaplib |
| **Inbox** | Monitoruje skrzynke, klasyfikuje odpowiedzi (HOT_LEAD / negatywna / opt-out) | IMAP + Gemini |

### Pipeline leadow

```
NEW → ANALYZED → DRAFTED → SENT → HOT_LEAD / REPLIED / NOT_INTERESTED / BOUNCED
```

Kazdy lead przechodzi przez caly pipeline autonomicznie. System sam decyduje kiedy przejsc do nastepnego kroku.

---

## Kluczowe funkcjonalnosci

### Sekwencja follow-upow (Drip Campaign)
- 3 maile w sekwencji: pierwszy mail → **6 dni przerwy** → follow-up #2 → **7 dni przerwy** → follow-up #3
- Jesli firma odpowie na **dowolnym** etapie — sekwencja jest natychmiast przerywana
- Follow-upy nie wliczaja sie do dziennego limitu wysylek

### Okienko wysylkowe
- Wysylanie maili tylko w godzinach **8:00–20:00** (czas polski)
- Poza okienkiem system przygotowuje leady na nastepny dzien (scouting, research, pisanie)
- W trybie AUTO — losowe opoznienia miedzy mailami (3–10 sekund), imitacja czlowieka

### Warmup (rozgrzewka domeny)
- Nowa skrzynka zaczyna od 2 maili dziennie
- Codziennie limit rosnie o 2 (konfigurowalny increment)
- Gdy warmup osiagnie `daily_limit` klienta — stabilizuje sie na tym poziomie

### Synchronizacja z Payload CMS (Brief Sync)
- Konfiguracja klientow pochodzi z Payload CMS (tabele `orders` + `briefs` we wspolnej bazie PostgreSQL)
- System co 30 minut sprawdza zmiany w briefach i aktualizuje dane klientow
- Automatyczne wykrywanie CO sie zmienilo (logowanie pol)
- Pola zarzadzane przez Nexus (modele LLM, stopka HTML z API gov.pl, dane KRS) nigdy nie sa nadpisywane przez sync

### Bezpieczenstwo i RODO
- Hasla SMTP/IMAP szyfrowane przez KMS, deszyfrowane tylko w momencie uzycia
- Po uzyciu haslo jest zerowane w pamieci (`ctypes.memset`)
- Kryptograficzna czarna lista opt-out (SHA-256, zero plain-text)
- Automatyczna anonimizacja leadow ktore prosza o wypisanie (art. 17 RODO)
- Klauzula RODO dodawana programatycznie do kazdego maila

### Statystyki (Campaign Statistics)
- Dzienne metryki per klient: scouting, research, wysylki, odpowiedzi, bounce'y
- UPSERT (jeden wiersz na klienta na dzien)
- Reply rate, positive rate, sredni czas odpowiedzi

---

## Stack technologiczny

| Warstwa | Technologia |
|---------|-------------|
| Jezyk | Python 3.12 |
| Baza danych | PostgreSQL 15 (Railway) |
| ORM | SQLAlchemy 2.0 |
| Cache / Kolejki | Redis 7 |
| Modele AI | Gemini 3.1 Pro/Flash, Claude, DeepSeek (fallback) |
| Framework AI | LangChain (SystemMessage/HumanMessage, structured output) |
| Scraping | Apify (Google Maps), Firecrawl (strony WWW) |
| Dashboard | Streamlit |
| Deploy | Docker Compose (PostgreSQL + Redis + Engine) |

---

## Struktura projektu

```
.
├── main.py                  # Glowna petla silnika (async dispatcher)
├── init_db.py               # Inicjalizacja bazy + migracje kolumn
├── docker-compose.yml       # PostgreSQL + Redis + Engine
├── pyproject.toml           # Zaleznosci (uv)
│
├── app/
│   ├── database.py          # Modele ORM (Client, Lead, Campaign, GlobalCompany, ...)
│   ├── brief_sync.py        # Synchronizacja Payload CMS → Client
│   ├── scheduler.py         # Follow-upy (Drip) + zapis draftow IMAP
│   ├── warmup.py            # Kalkulator dziennego limitu (rozgrzewka)
│   ├── rodo_manager.py      # Czarna lista opt-out + anonimizacja + klauzula RODO
│   ├── kms_client.py        # Szyfrowanie/deszyfrowanie credentiali
│   ├── krs_api.py           # Integracja z API KRS/REGON (gov.pl)
│   ├── model_factory.py     # Abstrakcja providerow LLM (Gemini/Claude/DeepSeek)
│   ├── stats_manager.py     # Metryki dzienne (UPSERT per client per day)
│   ├── schemas.py           # Pydantic schemas (structured output)
│   ├── backup_manager.py    # Automatyczne backupy PostgreSQL
│   ├── cache_manager.py     # Redis cache (Firecrawl, warmup)
│   ├── queue_manager.py     # Redis kolejki (multi-instance)
│   ├── rate_limiter.py      # Rate limiting API
│   └── agents/
│       ├── strategy.py      # Generowanie zapytan wyszukiwania
│       ├── scout.py         # Wyszukiwanie firm + AI Gatekeeper
│       ├── researcher.py    # Deep research + ekstrakcja danych
│       ├── writer.py        # Generowanie maili + montaz (body + podpis + stopka + RODO)
│       ├── sender.py        # Wysylka SMTP (SSL/TLS)
│       ├── inbox.py         # Monitoring skrzynki (odpowiedzi, bounce, opt-out)
│       └── reporter.py      # Generowanie raportow PDF
│
├── gui/
│   └── dashboard.py         # Panel Streamlit (zarzadzanie klientami, kampaniami, podglad)
│
└── files/                   # Zalaczniki, raporty, loga kampanii
```

---

## Uruchomienie

### Wymagania
- Python 3.12+
- PostgreSQL 15+
- Redis 7+ (opcjonalny, ale zalecany)

### Instalacja

```bash
# Klonowanie
git clone <repo-url>
cd "Agent TITAN BOT"

# Srodowisko Python (uv)
uv sync

# Konfiguracja
cp .env.example .env
# Uzupelnij: DATABASE_URL, GEMINI_API_KEY, APIFY_API_TOKEN, FIRECRAWL_API_KEY

# Inicjalizacja bazy
python init_db.py

# Uruchomienie silnika
python main.py

# Dashboard (osobny terminal)
uv run streamlit run gui/dashboard.py
```

### Docker

```bash
docker-compose up -d
```

Uruchamia PostgreSQL + Redis. Silnik (`main.py`) i dashboard uruchamiasz osobno.

---

## Konfiguracja (.env)

```env
DATABASE_URL=postgresql://user:pass@host:5432/dbname
GEMINI_API_KEY=...
APIFY_API_TOKEN=...
FIRECRAWL_API_KEY=...

# Opcjonalne
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=...          # Fallback na Claude
DEEPSEEK_API_KEY=...           # Fallback na DeepSeek
```

---

## Aktualny stan projektu

### Zrealizowane
- Pelny pipeline 5 agentow (Scout → Researcher → Writer → Sender → Inbox)
- Sekwencja 3 follow-upow z rozciagnietymi interwałami (6 + 7 dni)
- Okienko wysylkowe 8:00–20:00 z imitacja ludzkiego zachowania
- Warmup domeny (stopniowe zwiekszanie limitu)
- Synchronizacja briefow z Payload CMS (auto-sync co 30 min + przy otwarciu dashboardu)
- Ochrona pol Nexus-managed (modele LLM, stopka, dane KRS) przed nadpisaniem przez sync
- Dashboard Streamlit (zarzadzanie klientami, kampaniami, podglad pipeline'u)
- Pelna zgodnosc z RODO (kryptograficzna czarna lista, anonimizacja, klauzula informacyjna)
- Integracja z API KRS/REGON (gov.pl) do generowania stopek
- Szyfrowanie credentiali (KMS) + secure wipe hasel w pamieci
- System statystyk dziennych (campaign_statistics)
- Redis cache (Firecrawl, warmup) + kolejki (opcjonalne)
- Automatyczne backupy PostgreSQL co 6 godzin
- Multi-model support (Gemini, Claude, DeepSeek) z fallbackiem per agent

### W trakcie / planowane
- Testy jednostkowe i integracyjne
- Endpoint API (FastAPI) do programatycznego dostepu
- Multi-instance deployment (Kubernetes)
- Integracja platnosci (Stripe) dla modelu SaaS

---

## Autor

**Kamil Kowalczuk** — [@KamilKowalczuk](https://github.com/KamilKowalczuk)

Licencja: MIT
