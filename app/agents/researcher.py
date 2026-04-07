# app/agents/researcher.py
"""
RESEARCHER V4: BULLDOZER + DEBOUNCE VERIFIER
NOW WITH: Redis cache for Firecrawl results (save $200/mc!)
"""

import os
import re
import httpx
import json
import logging
import html
import asyncio
import concurrent.futures
from datetime import datetime
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv

# Importy z aplikacji
from app.database import Lead, GlobalCompany
from app.tools import verify_email_mx, verify_email_deep, get_main_domain_url
from app.schemas import CompanyResearch
from app.cache_manager import cache_manager
from app.rodo_manager import is_domain_opted_out
from app.model_factory import create_structured_llm, DEFAULT_MODEL
from app import stats_manager

# Konfiguracja loggera
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("researcher")

load_dotenv()

# Konfiguracja API
firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

if not firecrawl_key:
    logger.error("❌ CRITICAL: Brak FIRECRAWL_API_KEY w .env. Researcher nie zadziała.")

# --- NARZĘDZIA POMOCNICZE ---

def extract_emails_from_html(raw_html: str) -> list:
    """Ekstrakcja z BRUDNEGO HTMLa (X-RAY)."""
    if not raw_html: return []
    
    text = html.unescape(raw_html)
    emails = []
    
    mailto_pattern = r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    emails.extend(re.findall(mailto_pattern, text))
    
    text_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails.extend(re.findall(text_pattern, text))
    
    unique = list(set(e.lower() for e in emails))
    clean = []
    
    # Kwarantanna: Twarde wykluczenie darmowych poczt domowych (Bramka B2B Only - UŚUDE)
    freemail_domains = [
        # --- POLSKIE (W tym subdomeny i aliasy korporacyjne WP/Onet/Interia) ---
    'wp.pl', 'o2.pl', 'onet.pl', 'onet.eu', 'op.pl', 'interia.pl', 'interia.eu', 'interia.com'
    'poczta.fm', 'tlen.pl', 'gazeta.pl', 'go2.pl', 'vp.pl', 'spoko.pl', 'vip.interia.pl', 
    'autograf.pl', 'int.pl', 'aqq.eu', 'poczta.onet.pl', 'poczta.wp.pl', 'pro.wp.pl', 
    'o2.eu', 'buziaczek.pl', 'amorki.pl', 'lubie.to', 'poczta.interia.pl',
    
    # --- GOOGLE ---
    'gmail.com', 'googlemail.com',
    
    # --- MICROSOFT ---
    'hotmail.com', 'outlook.com', 'live.com', 'msn.com', 'windowslive.com', 'passport.com',
    'outlook.eu', 'hotmail.co.uk', 'live.co.uk', # popularne rozszerzenia w EU
    
    # --- YAHOO & AOL ---
    'yahoo.com', 'ymail.com', 'rocketmail.com', 'aol.com', 'aim.com', 
    'yahoo.co.uk', 'yahoo.pl',
    
    # --- APPLE ---
    'icloud.com', 'me.com', 'mac.com',
    
    # --- BEZPIECZNE / SZYFROWANE (Często używane do ukrywania tożsamości) ---
    'protonmail.com', 'protonmail.ch', 'proton.me', 'pm.me', 
    'tutanota.com', 'tutanota.de', 'tutamail.com', 'tuta.io', 'keemail.me',
    
    # --- INNE GLOBALNE ---
    'mail.com', 'zoho.com', 'zoho.eu', 'yandex.com', 'yandex.ru', 
    'gmx.com', 'gmx.net', 'gmx.de', 'fastmail.com', 'fastmail.fm', 'hey.com',
    'inbox.com', 'mail.ru', 'qq.com', '163.com', '126.com', 'sina.com'
    ]
    
    for email in unique:
        domain_part = email.split('@')[-1] if '@' in email else ""
        if domain_part in freemail_domains:
            continue
        
        if email.endswith(('.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.woff', '.webp', '.mp4')): continue
        if any(x in email for x in ['sentry', 'noreply', 'no-reply', 'example', 'domain', 'email.com', 'bootstrap', 'react']): continue
        if len(email) < 5 or len(email) > 60: continue
        clean.append(email)
        
    return clean


class TitanScraper:
    """Klient Firecrawl - Tryb Async (HTTPX)."""
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.firecrawl.dev/v1"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def scrape(self, url): 
        if not self.api_key: return None
        
        endpoint = f"{self.base_url}/scrape"
        payload = {
            "url": url, 
            "formats": ["markdown", "html"], 
            "onlyMainContent": False, 
            "timeout": 20000,
            "excludeTags": ["script", "style", "video", "canvas"] 
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(endpoint, headers=self.headers, json=payload)
                if response.status_code == 200:
                    data = response.json().get('data', {})
                    if not data.get('markdown') and not data.get('html'):
                        return None
                    return {
                        "markdown": data.get('markdown', ""),
                        "html": data.get('html', "")
                    }
                elif response.status_code == 429:
                    logger.warning(f"⚠️ RATE LIMIT (429) dla {url}. Zwalniam...")
                    return None
                return None
            except Exception as e:
                logger.error(f"Błąd scrapowania {url}: {e}")
                return None

    async def map_site(self, url): 
        if not self.api_key: return []
        
        endpoint = f"{self.base_url}/map"
        payload = {"url": url, "search": "contact about team career kontakt o-nas zespol kariera"}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(endpoint, headers=self.headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data.get('links', []) or data.get('data', {}).get('links', [])
                return []
            except:
                return []


scraper = TitanScraper(firecrawl_key)


def _run_async_safe(coro, timeout: int = 120):
    """
    Bezpiecznie uruchamia korutynę asynchroniczną z kontekstu synchronicznego.

    Tworzy świeży wątek z własnym event loop, co eliminuje błąd
    'This event loop is already running' (np. w Streamlit lub gdy
    funkcja jest wołana przez asyncio.to_thread z głównego loopa).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=timeout)


async def _parallel_scrape(urls: list) -> dict: 
    combined_markdown = ""
    all_html_emails = []
    
    urls = list(set(urls))
    
    print(f"         🚀 Uruchamiam {len(urls)} zadań async scrapingowych (z opóźnieniem)...")
    
    tasks = []
    for url in urls:
        # Dodajemy opóźnienie 1s, żeby nie uderzyć w 5 endpointów w 1ms
        tasks.append(scraper.scrape(url))
        await asyncio.sleep(1.0) # <--- RATE LIMIT FIX (1s delay)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        url = urls[i]
        
        if isinstance(result, Exception):
            logger.error(f"Błąd zadania {url}: {result}")
            continue
            
        if result:
            if result.get("html"):
                found = extract_emails_from_html(result["html"])
                if found:
                    print(f"            👀 Znaleziono w HTML ({url}): {found}")
                    all_html_emails.extend(found)
            
            md = result.get("markdown", "")
            if len(md) > 50:
                section_name = "STRONA"
                if "contact" in url or "kontakt" in url: section_name = "KONTAKT"
                elif "about" in url or "o-nas" in url: section_name = "O NAS"
                
                combined_markdown += f"\n\n=== {section_name} ({url}) ===\n{md[:15000]}"
                
    return {
        "markdown": combined_markdown,
        "regex_emails": list(set(all_html_emails))
    }


async def _get_content_titan_strategy(url: str, domain: str) -> dict:
    """
    Strategia BULLDOZER: Mapowanie + Wymuszone Ścieżki (Async).
    NOW WITH: Redis cache for scraping results.
    
    Args:
        url: Full URL to scrape
        domain: Clean domain name (for cache key)
    
    Returns:
        {"markdown": "...", "regex_emails": [...]}
    """
    
    # ==========================================
    # STEP 1: CHECK REDIS CACHE
    # ==========================================
    cached = cache_manager.get_company_scraping(domain)
    if cached:
        logger.info(f"⚡ CACHE HIT: Scraping for {domain} (saved Firecrawl API call!)")
        return {
            "markdown": cached.get("markdown", ""),
            "regex_emails": cached.get("regex_emails", [])
        }
    
    logger.info(f"💸 CACHE MISS: {domain} → calling Firecrawl API")
    
    # ==========================================
    # STEP 2: NO CACHE - DO ACTUAL SCRAPING
    # ==========================================
    print(f"      🔥 [TITAN] Cel: {url}")
    
    base_url = url.rstrip('/')
    forced_pages = [
        base_url,
        f"{base_url}/kontakt",
        f"{base_url}/contact",
        f"{base_url}/o-nas",
        f"{base_url}/about"
    ]
    
    mapped_links = await scraper.map_site(url)
    final_list = forced_pages.copy()
    
    if mapped_links:
        keywords = ["team", "zespol", "kariera", "career", "praca"]
        interesting = [l for l in mapped_links if any(k in l.lower() for k in keywords)]
        final_list.extend(interesting[:2])

    clean_urls = []
    seen = set()
    for u in final_list:
        if u in seen: continue
        if any(ext in u.lower() for ext in ['.pdf', '.jpg', '.png', '#']): continue
        clean_urls.append(u)
        seen.add(u)

    clean_urls.sort(key=lambda x: 0 if 'kontakt' in x or 'contact' in x else 1)
    target_urls = clean_urls[:5]

    print(f"         🎯 Lista celów: {[u.split('/')[-1] for u in target_urls]}")
    
    # Actual scraping
    scraping_result = await _parallel_scrape(target_urls)
    
    # ==========================================
    # STEP 3: CACHE THE RESULT
    # ==========================================
    cache_data = {
        "markdown": scraping_result["markdown"],
        "regex_emails": scraping_result["regex_emails"],
        "scraped_urls": target_urls,
        "url_count": len(target_urls)
    }
    
    cache_manager.set_company_scraping(domain, cache_data)
    logger.info(f"✅ Cached scraping result for {domain} (14 days TTL)")
    
    return scraping_result


def analyze_lead(session: Session, lead_id: int):
    """
    RESEARCHER V4: BULLDOZER + DEBOUNCE VERIFIER + REDIS CACHE.
    """
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead: return

    company = lead.company
    client = lead.campaign.client
    mode = getattr(client, "mode", "SALES")

    # --- BLACKLIST CHECK (przed wydaniem kredytu Firecrawl) ---
    if is_domain_opted_out(session, company.domain or ""):
        logger.warning(
            f"[RESEARCHER] Domena '{company.domain}' na blackliście RODO — pomijam research."
        )
        lead.status = "BLACKLISTED"
        session.commit()
        return

    print(f"\n   🔎 [RESEARCHER {mode}] Analiza: {company.name}")
    # STATS: lead analyzed
    stats_manager.increment_analyzed(session, client.id)

    # Dynamiczny model z konfiguracji klienta
    researcher_model = getattr(client, "researcher_model", None) or DEFAULT_MODEL
    structured_llm = create_structured_llm(researcher_model, CompanyResearch, temperature=0.1)
    logger.info(f"[RESEARCHER] Model: {researcher_model}")

    target_url = get_main_domain_url(company.domain)
    if not target_url.startswith("http"): target_url = "https://" + target_url

    # 1. POBIERANIE (Async in Sync) - NOW WITH CACHE!
    try:
        scan_result = _run_async_safe(
            _get_content_titan_strategy(target_url, company.domain)
        )
    except Exception as e:
        logger.error(f"      ❌ Błąd Async w Research: {e}", exc_info=True)
        scan_result = {"markdown": "", "regex_emails": []}
    
    content_md = scan_result["markdown"]
    regex_emails = scan_result["regex_emails"]

    if not content_md and not regex_emails:
        print(f"      ❌ PUSTY ZWIAD. Próba 404.")
        lead.status = "MANUAL_CHECK"
        session.commit()
        return

    # 2. ANALIZA AI — SHERLOCK MODE
    print(f"      🧠 Gemini analizuje dane...")

    regex_hint = ""
    if regex_emails:
        regex_hint = (
            f"\n=== TWARDE DOWODY Z HTML (REGEX) ===\n"
            f"W kodzie źródłowym znaleziono te emaile: {', '.join(regex_emails)}\n"
            f"To FAKTY — musisz je uwzględnić. Oceń do kogo należą.\n"
        )

    if mode == "JOB_HUNT":
        system_prompt = f"""Jesteś wywiadowcą rynku pracy. Analizujesz stronę WWW firmy jak detektyw — szukasz FAKTÓW, nie wrażeń.
{regex_hint}
=== CO MUSISZ ZNALEŹĆ ===

1. EMAILE (priorytet absolutny):
   - Imienne (jan.kowalski@) > ogólne (hr@, rekrutacja@) > biuro@
   - Pomiń: noreply@, privacy@, rodo@, webmaster@
   - Przeszukaj sekcje: Kontakt, Team, Kariera, stopka strony

2. TECH STACK (konkretnie):
   - Szukaj dosłownych nazw: "Python", "React", "AWS", "Docker", "Kubernetes"
   - NIE zgaduj z designu strony. Tylko jeśli WYMIENIONE na stronie.
   - Szukaj też w ofertach pracy (tam technologie są listowane wprost)

3. HIRING SIGNALS:
   - Czy mają zakładkę Kariera/Jobs? Ile ofert?
   - Czy szukają seniorów czy juniorów? (sygnał o budżecie)
   - Czy copyright w stopce jest aktualny (2025/2026)?

4. DECYDENCI (TYLKO z sekcji Zespół/Team/O nas):
   - Jeśli nie ma takiej sekcji → puste []
   - NIE wymyślaj. Jeśli strona nie pokazuje ludzi → puste.

5. VERIFIED_CONTACT_NAME — RYGORY:
   - TYLKO gdy: (a) imię w sekcji Zespół + (b) email pasujący do tej osoby na stronie
   - Wpisz IMIĘ (np. "Renata"). Jeśli warunki niespełnione → NULL.

6. ICEBREAKER — KONKRETNY FAK ze strony:
   - Dobry: "Widzę że szukacie Senior Python Deva — pracuję z FastAPI od 3 lat"
   - Zły: "Wasza firma robi świetną robotę"
   - Jeśli brak konkretu → "Brak"

7. SUMMARY — 2 zdania:
   - Zdanie 1: Czym DOKŁADNIE się zajmują (nie "firma technologiczna" ale "budują aplikacje mobilne dla fintechów")
   - Zdanie 2: Co wyróżnia / czym się chwalą

ZERO zmyślonych faktów. Lepiej puste pole niż halucynacja."""

    else:
        system_prompt = f"""Jesteś Sherlockiem Holmesem corporate intelligence. Dostajesz surowe dane ze strony WWW firmy i musisz z nich wyciągnąć KAŻDY fakt użyteczny dla handlowca, który będzie pisał do tej firmy cold maila.

Twoja analiza decyduje o jakości maila. Bzdury = bzdurny mail. Konkrety = mail na który odpisują.
{regex_hint}
=== CO MUSISZ WYCIĄGNĄĆ ===

1. EMAILE (to twój priorytet nr 1):
   - Imienne (jan.kowalski@, j.kowalska@) → najcenniejsze
   - Firmowe ogólne (biuro@, kontakt@, hello@, info@) → akceptowalne
   - ODRZUĆ: noreply@, privacy@, rodo@, webmaster@, marketing@ (autoresponder)
   - SZUKAJ W: sekcja Kontakt, stopka, nagłówek, sekcja Team, zakładka Kariera
   - Przeczytaj uważnie mailto: linki w HTML

2. DECYDENCI — WYŁĄCZNIE Z SEKCJI ZESPÓŁ/TEAM/O NAS:
   - Szukaj sekcji: "Zespół", "Team", "O nas", "About Us", "Nasi eksperci", "Nasi lekarze"
   - Zapisz: "Imię Nazwisko (Rola)" — np. "Jan Kowalski (CEO)"
   - Jeśli NIE MA sekcji zespołu → puste []. ZERO zgadywania.

3. VERIFIED_CONTACT_NAME — PODWÓJNY WARUNEK:
   - Wypełnij TYLKO gdy JEDNOCZEŚNIE:
     (a) Znalazłeś imię w sekcji Zespół/Team/O nas
     (b) Na tej samej stronie jest email pasujący do osoby (renata@, r.kowalska@, renata.kowalska@)
   - Wpisz TYLKO imię (np. "Renata"). Jeśli choć jeden warunek nie spełniony → NULL.

4. SUMMARY — dwa zdania na poziomie dyrektora:
   - Zdanie 1: Co KONKRETNIE robi firma (nie "oferuje usługi" ale "produkuje systemy ERP dla logistyki")
   - Zdanie 2: Czym się wyróżniają / co podkreślają (klienci, nagrody, skala, specjalizacja)

5. KEY_PRODUCTS — lista produktów/usług:
   - Przepisuj DOSŁOWNIE z menu / sekcji "Oferta" / "Usługi"
   - Nie uogólniaj. "Audyt SEO", "Pozycjonowanie lokalne", "Google Ads" zamiast "Marketing internetowy"

6. ICEBREAKER — KONKRETNY PUNKT ZACZEPIENIA:
   - Musi opierać się na fakcie ze strony, który handlowiec może zacytować
   - DOBRE: "Widzę że uruchomiliście nowy oddział w Gdańsku", "Szukacie CTO — to zwykle moment szybkiego wzrostu"
   - ZŁE: "Wasza firma jest interesująca", "Gratuluję świetnej strony"
   - Jeśli nie ma nic konkretnego → wpisz "Brak" (lepsze niż wymysł)
   - Szukaj: nowe oferty pracy, nagrody, nowe produkty, ekspansja, partnerstwa, eventy

7. PAIN_POINTS / OPPORTUNITIES — 2-3 punkty zaczepienia sprzedażowego:
   - Co może ich boleć? (np. "Szukają 3 handlowców → potrzebują leadów", "Strona wygląda na 5 lat → potrzeba redesignu")
   - Szukaj sygnałów: rekrutacja (wzrost), stara strona (potrzeba modernizacji), brak social media (potrzeba marketingu)

8. TECH STACK:
   - TYLKO technologie WPROST wymienione na stronie (Python, WordPress, SAP, HubSpot)
   - NIE zgaduj z wyglądu strony

9. HIRING SIGNALS:
   - Kogo szukają? Ile ofert? Jakie stanowiska?
   - To mówi o budżecie i kierunku rozwoju firmy

=== ŻELAZNE REGUŁY ===
- ZERO halucynacji. Każdy fakt musi mieć źródło na stronie.
- Puste pole > zmyślony fakt. Zawsze.
- Jeśli strona ma mało treści — wyciągnij co się da, resztę zostaw pustą.
- Nie powtarzaj tych samych informacji w różnych polach."""

    try:
        research = structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=content_md[:70000]),
        ])
    except Exception as e:
        print(f"      ❌ Błąd LLM: {e}")
        # Ratunek HTML w przypadku błędu LLM
        if regex_emails:
            print("      ⚠️ LLM Error. Ratuję lead mailami z HTML.")
            # Sprawdzamy pierwszy mail w trybie awaryjnym
            status = verify_email_deep(regex_emails[0])
            if status == "INVALID":
                lead.status = "MANUAL_CHECK"
                print("      💀 Email z HTML jest INVALID.")
            else:
                lead.target_email = regex_emails[0]
                lead.status = "ANALYZED"
                lead.ai_confidence_score = 40
                lead.ai_analysis_summary = f"HTML RESCUE MODE. Status: {status}"
            session.commit()
            return
        lead.status = "MANUAL_CHECK"
        session.commit()
        return

    # 3. SCORING & SELECTION
    combined_emails = list(set((research.contact_emails or []) + regex_emails))
    
    def score_email(email):
        s = 0
        e = email.lower()
        if mode == "JOB_HUNT":
            if any(x in e for x in ['kariera', 'jobs', 'rekrutacja', 'hr', 'people']): s += 20
            if any(x in e for x in ['cto', 'tech', 'engineering']): s += 25
            if any(x in e for x in ['ceo', 'founder']): s += 15
        else:
            if any(x in e for x in ['ceo', 'owner', 'founder', 'prezes']): s += 20
            if any(x in e for x in ['kariera', 'jobs', 'rekrutacja']): s -= 20 
            
        if any(x in e for x in ['biuro', 'info', 'hello', 'kontakt', 'office']): s += 15
        if '.' in e.split('@')[0]: s += 5
        # Tu używamy tylko darmowego MX check do sortowania (nie płacimy jeszcze)
        if not verify_email_mx(e): s -= 100 
        return s

    scored = []
    if combined_emails:
        scored = sorted([(e, score_email(e)) for e in combined_emails], key=lambda x: x[1], reverse=True)
        print(f"      📧 Scoring [{mode}]: {scored}")
        # STATS: emails found
        stats_manager.increment_emails_found(session, client.id, len(combined_emails))

    # 4. DEEP VERIFICATION (DeBounce Loop) - NOW WITH CACHE from tools.py!
    
    final_email = None
    verification_note = ""
    
    for candidate, score in scored:
        if score < -20: continue # Szkoda kasy na śmieci
        
        print(f"      🛡️ Weryfikacja DeBounce dla: {candidate}...")
        status = verify_email_deep(candidate)  # ← This now uses Redis cache!
        
        if status in ["OK", "RISKY"]:
            final_email = candidate
            verification_note = f"[VERIFIED: {status}]"
            # STATS: email verified
            stats_manager.increment_verified(session, client.id)
            if status == "OK":
                print("         ✅ Adres POPRAWNY.")
            else:
                print("         ⚠️ Adres RYZYKOWNY (Catch-All/Role), ale akceptowalny.")
            break # Mamy zwycięzcę
        else:
            print(f"         ❌ Adres INVALID/SPAMTRAP. Próbuję następny...")

    if not final_email and scored:
        verification_note = "All emails failed verification."

    # 5. ZAPIS
    company.tech_stack = research.tech_stack
    company.decision_makers = research.decision_makers
    company.industry = research.target_audience
    company.last_scraped_at = datetime.now(PL_TZ)
    
    verified_name = (research.verified_contact_name or "").strip() or None

    lead.ai_analysis_summary = (
        f"MODE: {mode}\n"
        f"VERIFIED_CONTACT_NAME: {verified_name or 'NULL'}\n"
        f"ICEBREAKER: {research.icebreaker}\n"
        f"SUMMARY: {research.summary}\n"
        f"KEY_PRODUCTS: {', '.join(research.key_products or [])}\n"
        f"PAIN_POINTS: {'; '.join(research.pain_points_or_opportunities or [])}\n"
        f"MAILS FOUND: {combined_emails}\n"
        f"HIRING: {research.hiring_signals}\n"
        f"VERIFICATION: {verification_note}"
    )
    
    if final_email:
        lead.target_email = final_email
        lead.status = "ANALYZED"
        # Dajemy wysoki score tylko jeśli weryfikacja była OK, niższy przy Catch-All
        lead.ai_confidence_score = 95 if "OK" in verification_note else 65
        print(f"      ✅ SUKCES: {final_email} {verification_note}")
    else:
        lead.status = "MANUAL_CHECK"
        lead.ai_confidence_score = 15
        print(f"      ⚠️ MANUAL CHECK (Brak poprawnego maila)")

    session.commit()


# --- ASYNC WRAPPER ---
async def analyze_lead_async(session: Session, lead_id: int):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, analyze_lead, session, lead_id)
