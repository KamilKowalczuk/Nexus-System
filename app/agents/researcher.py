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
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Importy z aplikacji
from app.database import Lead, GlobalCompany
from app.tools import verify_email_mx, verify_email_deep, get_main_domain_url
from app.alerts import send_operator_alert
from app import critical_monitor
from app.schemas import CompanyResearch
from app.cache_manager import cache_manager
from app.rodo_manager import is_domain_opted_out
from app.model_factory import create_structured_llm, create_llm, DEFAULT_MODEL
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
    """Ekstrakcja z BRUDNEGO HTMLa (X-RAY). Odporny na placeholder emaile z formularzy."""
    if not raw_html: return []

    text = html.unescape(raw_html)

    # STEP 0: Wyciągnij placeholdery z atrybutów HTML formularzy.
    # Adresy w placeholder/value inputów to ZAWSZE przykłady — nigdy nie piszemy do nich.
    form_placeholder_emails: set[str] = set()
    _placeholder_patterns = [
        r'placeholder=["\']([^"\']{4,80})["\']',
        r'<input[^>]*type=["\'](?:email|text)["\'][^>]*value=["\']([^"\']{4,80})["\']',
        r'<input[^>]*value=["\']([^"\']{4,80})["\'][^>]*type=["\'](?:email|text)["\']',
    ]
    for pattern in _placeholder_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            candidate = match.group(1).strip().lower()
            if '@' in candidate:
                form_placeholder_emails.add(candidate)

    if form_placeholder_emails:
        logger.debug(f"[RESEARCHER] Placeholdery formularzy (blokada): {form_placeholder_emails}")

    emails = []
    mailto_pattern = r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    emails.extend(re.findall(mailto_pattern, text))

    text_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails.extend(re.findall(text_pattern, text))

    unique = list(set(e.lower() for e in emails))
    clean = []
    
    # Kwarantanna: Twarde wykluczenie darmowych poczt domowych (Bramka B2B Only)
    # freemail_domains = {
    #     # --- POLSKIE ---
    #     'wp.pl', 'o2.pl', 'onet.pl', 'onet.eu', 'op.pl', 'interia.pl', 'interia.eu', 'interia.com',
    #     'poczta.fm', 'tlen.pl', 'gazeta.pl', 'go2.pl', 'vp.pl', 'spoko.pl', 'vip.interia.pl',
    #     'autograf.pl', 'int.pl', 'aqq.eu', 'poczta.onet.pl', 'poczta.wp.pl', 'pro.wp.pl',
    #     'o2.eu', 'buziaczek.pl', 'amorki.pl', 'lubie.to', 'poczta.interia.pl',
    #     # --- GOOGLE ---
    #     'gmail.com', 'googlemail.com',
    #     # --- MICROSOFT ---
    #     'hotmail.com', 'outlook.com', 'live.com', 'msn.com', 'windowslive.com', 'passport.com',
    #     'outlook.eu', 'hotmail.co.uk', 'live.co.uk',
    #     # --- YAHOO & AOL ---
    #     'yahoo.com', 'ymail.com', 'rocketmail.com', 'aol.com', 'aim.com',
    #     'yahoo.co.uk', 'yahoo.pl',
    #     # --- APPLE ---
    #     'icloud.com', 'me.com', 'mac.com',
    #     # --- BEZPIECZNE / SZYFROWANE ---
    #     'protonmail.com', 'protonmail.ch', 'proton.me', 'pm.me',
    #     'tutanota.com', 'tutanota.de', 'tutamail.com', 'tuta.io', 'keemail.me',
    #     # --- INNE GLOBALNE ---
    #     'mail.com', 'zoho.com', 'zoho.eu', 'yandex.com', 'yandex.ru',
    #     'gmx.com', 'gmx.net', 'gmx.de', 'fastmail.com', 'fastmail.fm', 'hey.com',
    #     'inbox.com', 'mail.ru', 'qq.com', '163.com', '126.com', 'sina.com',
    # }

    # Wzorce placeholder/przykładowych emaili z formularzy kontaktowych
    _PLACEHOLDER_LOCAL_PARTS = {
        'your', 'yourname', 'youremail', 'yourmail', 'name', 'email', 'mail',
        'adres', 'twoj', 'twojmail', 'twojemail', 'uzytkownik', 'user',
        'test', 'demo', 'sample', 'placeholder', 'example', 'admin123',
    }

    for email in unique:
        parts = email.split('@')
        if len(parts) != 2:
            continue
        local, domain_part = parts[0], parts[1]

        # Blokada emaili wyciągniętych z atrybutów placeholder/value formularzy
        if email in form_placeholder_emails:
            logger.debug(f"[RESEARCHER] Odrzucono placeholder formularza: {email}")
            continue

        # [DISABLED] Freemail blocking - zakomentowane bo małe placówki używają gmail.com jako firmowego
        # if domain_part in freemail_domains:
        #     continue

        if email.endswith(('.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.woff', '.webp', '.mp4')):
            continue

        # Blokada śmieciowych słów kluczowych w całym adresie
        if any(x in email for x in ['sentry', 'noreply', 'no-reply', 'example.com', 'example.pl',
                                      'bootstrap', 'react', 'webmaster', 'donotreply', 'do-not-reply',
                                      'spam', 'test@', 'demo@', 'sample@', 'rodo', 'iod@', 'iodo@', 'dpo@', 'inspektor']):
            continue

        # Blokada placeholderów w części lokalnej (np. "email@firma.pl", "your@firma.pl")
        if local.lower() in _PLACEHOLDER_LOCAL_PARTS:
            continue

        if len(email) < 6 or len(email) > 60:
            continue

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
                    critical_monitor.record_success("firecrawl")
                    return {
                        "markdown": data.get('markdown', ""),
                        "html": data.get('html', "")
                    }
                elif response.status_code == 429:
                    logger.warning(f"⚠️ RATE LIMIT (429) dla {url}. Zwalniam...")
                    return None
                elif response.status_code in (402, 401):
                    # Brak kredytów lub nieprawidłowy klucz — natychmiastowy stop
                    critical_monitor.trigger_stop(
                        api_name="firecrawl",
                        reason=f"Firecrawl API zwróciło HTTP {response.status_code} — "
                               f"{'wyczerpane kredyty' if response.status_code == 402 else 'nieprawidłowy klucz API'}.",
                        consecutive=1,
                    )
                    return None
                else:
                    critical_monitor.record_failure("firecrawl")
                    return None
            except Exception as e:
                logger.error(f"Błąd scrapowania {url}: {e}")
                critical_monitor.record_failure("firecrawl")
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

    async def search(self, query): 
        if not self.api_key: return ""
        endpoint = f"{self.base_url}/search"
        payload = {"query": query, "limit": 3}
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(endpoint, headers=self.headers, json=payload)
                if response.status_code == 200:
                    raw = response.json()
                    # Firecrawl Search API zwraca albo {"data": [...]} albo bezpośrednio [...]
                    if isinstance(raw, dict):
                        data = raw.get('data', [])
                    elif isinstance(raw, list):
                        data = raw
                    else:
                        return ""
                    if not data:
                        return ""
                    snippets = []
                    for d in data:
                        if isinstance(d, dict):
                            snippets.append(f"- {d.get('title', '')}: {d.get('description', '')}")
                        elif isinstance(d, str):
                            snippets.append(f"- {d}")
                    return "\n".join(snippets)
                return ""
            except:
                return ""

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


def _is_splash_screen(md: str) -> bool:
    """
    Wykrywa strony-selectory lokalizacji / splash screeny.
    Firmy z wieloma placówkami często mają stronę główną z przyciskami
    'Wybierz lokalizację' / 'Wybierz placówkę' zamiast prawdziwej treści.
    """
    if not md:
        return True
    md_lower = md.lower()
    splash_patterns = [
        "wybierz swoją placówkę",
        "wybierz placówkę",
        "wybierz lokalizację",
        "wybierz oddział",
        "wybierz miasto",
        "wybierz filię",
        "select location",
        "choose your location",
        "select branch",
        "wejdź »",
        "wejdź »",
    ]
    # Jeśli strona zawiera którykolwiek wzorzec splash screena
    for pattern in splash_patterns:
        if pattern in md_lower:
            return True
    return False


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
        cached_md = cached.get("markdown", "")
        # Detekcja splash screen w cache — wzorce selectorów lokalizacji
        is_splash = _is_splash_screen(cached_md)
        if not is_splash and len(cached_md) >= 500:
            logger.info(f"⚡ CACHE HIT: Scraping for {domain} (saved Firecrawl API call!)")
            return {
                "markdown": cached_md,
                "regex_emails": cached.get("regex_emails", [])
            }
        else:
            reason = "splash screen" if is_splash else f"thin ({len(cached_md)} chars)"
            logger.info(f"⚠️ CACHE INVALIDATED ({reason}): {domain} → re-scraping")
            cache_manager.delete_company_scraping(domain)
    
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
    # STEP 2b: SPLASH SCREEN / LOCATION SELECTOR DETECTOR
    # Jeśli strona główna jest "cienka" (selector lokalizacji, splash page z przyciskami),
    # scrapujemy stronę główną osobno, wyciągamy z HTML WSZYSTKIE wewnętrzne linki
    # (symulacja "kliknięcia w przycisk") i scrapujemy je głębiej.
    # ==========================================
    md_content = scraping_result.get("markdown", "")
    if _is_splash_screen(md_content) or len(md_content) < 500:
        print(f"         ⚠️ SPLASH SCREEN DETECTED: {len(md_content)} znaków. Szukam linków w HTML...")
        
        # 1. Scrapuj stronę główną osobno żeby wyciągnąć surowy HTML
        homepage = await scraper.scrape(base_url)
        deeper_urls = []
        
        if homepage and homepage.get("html"):
            raw_html = homepage["html"]
            # 2. Wyciągnij WSZYSTKIE linki <a href="..."> z HTML
            import re as _re
            href_pattern = r'<a[^>]+href=["\']([^"\'#]+)["\']'
            all_hrefs = _re.findall(href_pattern, raw_html, _re.IGNORECASE)
            
            for href in all_hrefs:
                # Odsiewamy: zewnętrzne linki, anchorsy, pliki statyczne
                if href.startswith("mailto:") or href.startswith("tel:"): 
                    continue
                if any(ext in href.lower() for ext in ['.pdf','.jpg','.png','.css','.js','.svg','.ico']): 
                    continue
                    
                # Buduj pełny URL z relatywnych ścieżek
                if href.startswith("/"):
                    full_url = f"https://{domain}{href}"
                elif href.startswith("http"):
                    # Tylko linki do tej samej domeny
                    if domain not in href: 
                        continue
                    full_url = href
                else:
                    full_url = f"{base_url}/{href}"
                
                if full_url not in seen:
                    deeper_urls.append(full_url)
                    seen.add(full_url)
        
        # Fallback: jeśli z HTML nic nie wyciągnęliśmy, próbuj mapped_links
        if not deeper_urls and mapped_links:
            for link in mapped_links:
                if link not in seen:
                    deeper_urls.append(link)
                    seen.add(link)
        
        deeper_urls = deeper_urls[:5]  # Limit: max 5 głębokich stron
        
        if deeper_urls:
            print(f"         🔍 Klikam w: {[u.split('/')[-1] or u.split('/')[-2] for u in deeper_urls]}")
            deep_result = await _parallel_scrape(deeper_urls)
            scraping_result["markdown"] += deep_result.get("markdown", "")
            scraping_result["regex_emails"] = list(set(
                scraping_result.get("regex_emails", []) + deep_result.get("regex_emails", [])
            ))
            print(f"         ✅ Po deep scrape: {len(scraping_result['markdown'])} znaków")
        else:
            print(f"         ❌ Brak linków do kliknięcia w HTML splash screena.")
    
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


class _GatekeeperVerdict(BaseModel):
    """Wewnętrzny model werdyktu post-scrape Gatekeepera."""
    approved: bool = Field(
        description="True jeśli firma SPEŁNIA wymagania klienta. False jeśli narusza zakazy lub jest całkowicie poza ICP."
    )
    reason: str = Field(
        description="Jedno zdanie uzasadniające decyzję."
    )


def _ai_gatekeeper_check(
    research: CompanyResearch,
    company_name: str,
    company_domain: str,
    client,
    researcher_model: str,
) -> tuple[bool, str]:
    """
    POST-SCRAPE GATEKEEPER: Weryfikuje czy firma — po pełnym zwiadzie strony WWW —
    nadal spełnia wymagania klienta (ICP + negative_constraints).

    Odrzuca "MARTWE STRONY" na podstawie research.data_currency_analysis.
    """
    constraints = (getattr(client, "negative_constraints", "") or "").strip()
    icp = (getattr(client, "ideal_customer_profile", "") or "").strip()
    industry = (getattr(client, "industry", "") or "").strip()
    current_year = datetime.now(PL_TZ).year

    hard_block_section = ""
    if constraints:
        hard_block_section = f"""
=== !! TWARDE ZAKAZY — BEZWZGLĘDNE !! ===
Zakazy firm do zastosowania:
{constraints}
Jeśli firma JAKKOLWIEK pasuje do zakazów firm → odrzuć (approved=False).
"""

    system_prompt = f"""Jesteś ostatnim filtrem przed wysłaniem cold maila B2B. Masz pełną wiedzę o firmie.
{hard_block_section}
=== PROFIL KLIENTA (czego szuka) ===
Branża: {industry}
Idealny profil klienta (ICP): {icp}

=== FIRMA DO OCENY ===
Nazwa: {company_name}
Domena: {company_domain}
Sygnały Krytyczne (z analizy strony): {", ".join(research.critical_business_signals) if research.critical_business_signals else "brak"}
Aktualność strony: {research.data_currency_analysis}
Czym się zajmuje: {research.summary}
Produkty/usługi: {", ".join(research.key_products or [])}

=== ZASADY OCENY ===
1. Jeśli firma ma negatywne "Sygnały Krytyczne" (np. nie przyjmuje nowych pacjentów, zawiesiła działalność, jest w likwidacji) → approved=False.
2. Jeśli firma narusza którykolwiek TWARDY ZAKAZ → approved=False, bez wyjątków.
3. Jeśli branża firmy jest CAŁKOWICIE INNA niż zakłada ICP (np. szukasz placówek medycznych, a trafiasz na IT, cyberbezpieczeństwo lub biuro rachunkowe) → approved=False. Nie naciągaj na siłę!
4. Jeśli firma choćby częściowo pasuje do ICP i nie narusza zakazów → approved=True.
5. W razie wątpliwości czy firma pasuje do targetu — ODRZUĆ (approved=False). Chronimy bazę przed spamowaniem przypadkowych firm.
6. MARTWE STRONY: WIEK strony NIE jest powodem do odrzucenia. Odrzucaj TYLKO przez zakazy, brak pacjentów lub ICP mismatch."""

    try:
        gatekeeper_llm = create_structured_llm(researcher_model, _GatekeeperVerdict, temperature=0.0)
        verdict = gatekeeper_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="Wydaj werdykt dla powyższej firmy."),
        ])
        return verdict.approved, verdict.reason
    except Exception as e:
        logger.error(f"[RESEARCHER GATEKEEPER] Błąd LLM: {e}", exc_info=True)
        return True, f"Błąd gatekeepera ({type(e).__name__}) — przepuszczono domyślnie."


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

    # === ANTY-CLOUDFLARE & ANTY-404 GUARD ===
    md_lower = content_md.lower()
    block_keywords = [
        "cloudflare", "verify you are a human", "checking your browser",
        "access denied", "error 404", "404 not found", "błąd 404", "nie znaleziono strony"
    ]
    # Odrzucamy zgryz jeśli strona jest krótka i wprost krzyczy o zablokowaniu
    if len(content_md) < 5000 and any(k in md_lower for k in block_keywords):
        print(f"      🛡️ WARN: Wykryto Firewall/404 dla {company.domain}. Odrzucam śmieciowy zwiad.")
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
        
    current_date_str = datetime.now(PL_TZ).strftime("%d %B %Y")
    current_year = datetime.now(PL_TZ).year
    
    time_context = f"=== BIEŻĄCA DATA: {current_date_str} ===\nWszystkie wyciągane przez Ciebie informacje poddawaj rygorowi czasu. Ignoruj wszystko, co zakończyło się rok temu lub wcześniej. "

    # ====================================================================
    # CLIENT DNA — pełny kontekst nadawcy wstrzyknięty do promptu
    # ====================================================================
    client_name = client.name or ""
    client_industry = client.industry or ""
    client_value_prop = client.value_proposition or ""
    client_icp = client.ideal_customer_profile or ""
    client_case_studies = client.case_studies or ""
    client_tone = (getattr(client, "tone_of_voice", None) or "").strip()
    client_constraints = (client.negative_constraints or "").strip()

    client_context = f"""=== 🎯 KONTEKST NADAWCY — W CZYIM IMIENIU SZUKASZ ===
Firma nadawcy: {client_name}
Branża nadawcy: {client_industry}
Co nadawca oferuje (VALUE PROPOSITION): {client_value_prop}
Kogo szuka (ICP): {client_icp}
Case studies / doświadczenie: {client_case_studies[:300] if client_case_studies else 'brak'}
Ton komunikacji: {client_tone or 'Profesjonalny'}
Czego NIE ROBIMY / zakazy: {client_constraints[:200] if client_constraints else 'brak'}

=== 🧠 INSTRUKCJA NADRZĘDNA ===
Nie jesteś generycznym skanerem stron. Jesteś EKSPERTEM w branży nadawcy ({client_industry}).
Twój CEL: znaleźć na stronie informacje, które ŁĄCZĄ SIĘ z ofertą nadawcy.
Szukasz MOSTU między tym co widzisz na stronie, a tym co nadawca może zaoferować.

Przykłady poprawnego myślenia:
- Nadawca oferuje rozliczenia NFZ → szukaj: kontrakty, programy zdrowotne, etaty, raportowanie, zakres POZ
- Nadawca robi strony WWW → szukaj: wiek strony, brak mobile, stary design, brak SSL
- Nadawca sprzedaje automatyzację AI → szukaj: procesy manualne, duży zespół, powtarzalne zadania
- Nadawca oferuje rekrutację → szukaj: oferty pracy, wakaty, tempo wzrostu zespołu

=== 🪦 MARTWE STRONY (HOOK, NIE WYROK) ===
Jeśli strona nie była aktualizowana od 2+ lat — TO JEST SYGNAŁ SPRZEDAŻOWY, nie powód do odrzucenia.
Zamiast ignorować, WYKORZYSTAJ to w icebreaker i pain_points:
- "Strona z 2020 roku → zasoby pochłania bieżąca administracja, nie marketing"
- "Brak aktualizacji online → zwykle koreluje z przeciążeniem procesów wewnętrznych"
Odrzuć lead TYLKO gdy strona jest całkowicie pusta (404, porzucona domena, zero treści)."""

    if mode == "JOB_HUNT":
        system_prompt = f"""Jesteś wywiadowcą rynku pracy. Analizujesz stronę WWW firmy jak detektyw — szukasz FAKTÓW, nie wrażeń.
{time_context}
{client_context}
{regex_hint}
=== CO MUSISZ ZNALEŹĆ ===

1. EMAILE (priorytet absolutny):
   - Imienne (jan.kowalski@) > ogólne (hr@, rekrutacja@) > biuro@
   - Pomiń: noreply@, privacy@, rodo@, webmaster@
   - Przeszukaj sekcje: Kontakt, Team, Kariera, stopka strony

2. TECH STACK (konkretnie):
   - Szukaj dosłownych nazw: "Python", "React", "AWS", "Docker", "Kubernetes"
   - NIE zgaduj z designu strony. Tylko jeśli WYMIENIONE na stronie.

3. HIRING SIGNALS:
   - Czy mają zakładkę Kariera/Jobs? Ile ofert?
   - Czy szukają seniorów czy juniorów?

4. DECYDENCI (TYLKO z sekcji Zespół/Team/O nas):
   - Jeśli nie ma takiej sekcji → puste []. NIE wymyślaj.

5. VERIFIED_CONTACT_NAME:
   - TYLKO gdy: (a) imię w sekcji Zespół + (b) email pasujący do tej osoby
   - Wpisz IMIĘ. Jeśli warunki niespełnione → NULL.

6. CRITICAL_BUSINESS_SIGNALS:
   - Szukaj informacji krytycznych blokujących współpracę, np.: "Tymczasowo wstrzymujemy zapisy nowych Pacjentów", "Brak przyjęć", "Gabinety zamknięte", "W likwidacji", "Działalność zawieszona".
   - Wypisz je DOSŁOWNIE z tekstu. Jeśli brak → opuść pole.

7. ICEBREAKER — MOST MIĘDZY OBSERWACJĄ A NADAWCĄ:
   - Znajdź fakt na stronie POWIĄZANY z kompetencjami nadawcy
   - Zbuduj z niego MOST: co widzisz → dlaczego to ważne w kontekście nadawcy
   - Jeśli brak konkretu powiązanego z nadawcą → "Brak"

7. SUMMARY — 2 zdania:
   - Zdanie 1: Czym DOKŁADNIE się zajmują
   - Zdanie 2: Co wyróżnia / czym się chwalą

ZERO zmyślonych faktów. Lepiej puste pole niż halucynacja."""

    else:
        system_prompt = f"""Jesteś niekwestionowanym ekspertem w branży: {client_industry}.
Dostajesz surowe dane ze strony WWW firmy i szukasz PRECYZYJNYCH punktów styku z ofertą nadawcy.
Twoja analiza decyduje o jakości maila. Bzdury = bzdurny mail. Konkrety = mail na który odpisują.
{time_context}
{client_context}
{regex_hint}
=== CO MUSISZ WYCIĄGNĄĆ ===

1. EMAILE (to twój priorytet nr 1):
   - Imienne (jan.kowalski@, j.kowalska@) → najcenniejsze
   - Firmowe ogólne (biuro@, kontakt@, hello@, info@) → akceptowalne
   - ODRZUĆ: noreply@, privacy@, rodo@, webmaster@, marketing@ (autoresponder)
   - Przeczytaj uważnie mailto: linki w HTML

2. DECYDENCI — WYŁĄCZNIE Z SEKCJI ZESPÓŁ/TEAM/O NAS:
   - Szukaj sekcji: "Zespół", "Team", "O nas", "Nasi eksperci", "Nasi lekarze"
   - Zapisz: "Imię Nazwisko (Rola)" — np. "Jan Kowalski (CEO)"
   - Jeśli NIE MA sekcji zespołu → puste []. ZERO zgadywania.

3. VERIFIED_CONTACT_NAME — PODWÓJNY WARUNEK:
   - Wypełnij TYLKO gdy JEDNOCZEŚNIE:
     (a) Znalazłeś imię w sekcji Zespół/Team/O nas
     (b) Na tej samej stronie jest email pasujący do osoby
   - Wpisz TYLKO imię (np. "Renata"). Jeśli choć jeden warunek nie spełniony → NULL.

4. SUMMARY — dwa zdania na poziomie dyrektora:
   - Zdanie 1: Co KONKRETNIE robi firma
   - Zdanie 2: Czym się wyróżniają / co podkreślają

5. KEY_PRODUCTS — lista produktów/usług:
   - Przepisuj DOSŁOWNIE z menu / sekcji "Oferta" / "Usługi"
   - Szukaj PRZEDE WSZYSTKIM produktów/usług POWIĄZANYCH z branżą nadawcy

6. ICEBREAKER — MOST MIĘDZY OBSERWACJĄ A OFERTĄ NADAWCY:
   - To NIE JEST "najciekawszy fakt ze strony". To fakt NAJBARDZIEJ POWIĄZANY z ofertą nadawcy.
   - Schemat myślenia: (1) Co widzę na stronie? (2) Jak to się łączy z tym co nadawca oferuje? (3) Gotowe zdanie.
   - DOBRE (nadawca = rozliczenia NFZ): "Widzę szeroką ofertę POZ z kontraktem NFZ — koordynacja tylu świadczeń to wyzwanie administracyjne"
   - DOBRE (nadawca = strony WWW): "Państwa strona nie była aktualizowana od 2020 roku — to często pierwszy sygnał, że warto odświeżyć obecność online"
   - ZŁE: "Fajnie że macie promocję na mezoterapię" (niezwiązane z ofertą nadawcy)
   - Jeśli ŻADEN fakt na stronie nie wiąże się z ofertą nadawcy → wpisz "Brak"
   - ZAWSZE opieraj się o AKTUALNE informacje. Nie chwytaj się starych programów/dotacji.
   - ⚠️ PROGRAMY ZDROWOTNE/RZĄDOWE (NFZ, UE, dotacje): Możesz wymienić program PO NAZWIE TYLKO gdy:
     (a) Nazwa programu jest WYRAŹNIE wymieniona na stronie tej placówki
     (b) Kontekst wskazuje że program jest AKTUALNIE realizowany (daty z bieżącego roku, aktywna rejestracja)
     Jeśli widzisz nazwę programu ale BEZ dat lub sygnałów aktywności → UOGÓLNIJ:
     ❌ "Realizują Państwo program Profilaktyka 40+" (może być nieaktualny!)
     ✅ "Przy tak szerokim zakresie kontraktów NFZ, koordynacja rozliczeń jest dużym wyzwaniem"

7. PAIN_POINTS / OPPORTUNITIES — 2-3 punkty W KONTEKŚCIE OFERTY NADAWCY:
   - Nie szukaj "bólu ogólnego". Szukaj bólu ZWIĄZANEGO z tym co nadawca może rozwiązać.
   - Nadawca = rozliczenia NFZ → "Szeroki zakres świadczeń POZ + specjaliści = złożone raportowanie"
   - Nadawca = strony WWW → "Strona z 2020, brak wersji mobilnej = utrata pacjentów szukających online"
   - Nadawca = AI automatyzacja → "Duży zespół + procesy manualne = pole do automatyzacji"
   - Każdy punkt MUSI łączyć obserwację ze strony z potencjalną potrzebą klienta związaną z nadawcą.

8. TECH STACK:
   - TYLKO technologie WPROST wymienione na stronie
   - NIE zgaduj z wyglądu strony

9. HIRING SIGNALS:
   - Kogo szukają? Ile ofert? Jakie stanowiska?

10. CRITICAL_BUSINESS_SIGNALS:
    - Szukaj informacji krytycznych blokujących współpracę (np. w aktualnościach/popupach).
    - Obejmuje: "Wstrzymujemy zapisy nowych Pacjentów / Klientów", "Placówka zamknięta do odwołania", "W likwidacji", "Zawieszenie działalności".
    - Cytuj fragment dosłownie. Jeśli brak takich sygnałów → leave empty list.

=== ŻELAZNE REGUŁY ===
- ZERO halucynacji. Każdy fakt musi mieć źródło na stronie.
- ODRZUĆ ŚMIECI SCRAPERA: Bezwzględnie zignoruj wszystkie techniczne błędy typu "Błąd 404", "Cloudflare", "Access Denied", "Nie znaleziono strony" — to brudy techniczne, a nie prawdziwe problemy firmy! Nigdy nie wymieniaj błędu 404 jako Pain Pointu, chyba że klient specjalizuje się w naprawie błędów serwerowych.
- Puste pole > zmyślony fakt. Zawsze.
- Jeśli strona ma mało treści — wyciągnij co się da, resztę zostaw pustą.
- Nie powtarzaj tych samych informacji w różnych polach.
- KAŻDA informacja którą wyciągasz musi być przydatna dla NADAWCY, nie dla Ciebie."""

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

    # ==========================================
    # 2a. AUDYTOR HALUCYNACJI (T=0)
    # ==========================================
    print("      🔍 Audytor weryfikuje Icebreaker i Pain Points (T=0)...")
    auditor_prompt = f"""Jesteś weryfikatorem faktów. Sprawdzasz czy to co wyciągnął researcher jest 100% oparte na tekście. Nie zgaduj.
Jeśli Icebreaker lub Pain Points przypisują firmie usługi/programy/cechy których nie ma na stronie (np. wymyślają nazwy systemów lub procesów, o których HTML nie wspomina) - natychmiast to odrzuć. Uważaj: jeśli tekst wspomina o danym programie, to NIE JEST to halucynacja.

FAKTY ZAWARTE W HTML (Surowy tekst):
{content_md[:70000]}

DO WERYFIKACJI:
ICEBREAKER: {research.icebreaker}
PAIN POINTS: {research.pain_points_or_opportunities}

Jeśli jakiekolwiek z tych twierdzeń to wymysły (nie znajdują potwierdzenia w FAKTACH), napisz 'HALLUCINATION'. 
Jeśli wszystkie opierają się na twardych danych zawartych powyżej, napisz 'VALID'.
Zwróć TYLKO to jedno słowo."""
    auditor_llm = create_llm(DEFAULT_MODEL, temperature=0.0)
    auditor_resp = auditor_llm.invoke([HumanMessage(content=auditor_prompt)])
    auditor_text = auditor_resp.content if isinstance(auditor_resp.content, str) else str(auditor_resp.content)

    if "HALLUCINATION" in auditor_text.upper():
        print("      🚫 AUDYTOR WYKRYŁ HALUCYNACJĘ! Czyszczę wymyślone informacje.")
        research.icebreaker = "Brak"
        research.pain_points_or_opportunities = ["Brak specyficznych danych na stronie — firma nie informuje szczegółowo o swoich procesach, co samo w sobie może być wstępem do rozmowy na żywo."]

    # 2b. POST-SCRAPE GATEKEEPER — weryfikacja po pełnym zwiadzie
    gk_approved, gk_reason = _ai_gatekeeper_check(
        research=research,
        company_name=company.name,
        company_domain=company.domain,
        client=client,
        researcher_model=researcher_model,
    )

    if not gk_approved:
        logger.warning(
            f"[RESEARCHER GATEKEEPER] Odrzucono {company.name} ({company.domain}): {gk_reason}"
        )
        print(f"      🚫 GATEKEEPER ODRZUCIŁ: {gk_reason}")
        lead.status = "MANUAL_CHECK"
        lead.ai_confidence_score = 0
        lead.ai_analysis_summary = (
            f"[GATEKEEPER ODRZUCIŁ — NIEZGODNE Z WYMAGANIAMI KLIENTA]\n"
            f"Powód: {gk_reason}\n"
            f"SUMMARY: {research.summary}"
        )
        session.commit()
        return

    print(f"      ✅ GATEKEEPER: Firma zatwierdzona. {gk_reason}")

    # 2c. FACT CHECKER ZEWNĘTRZNY DLA ICEBREAKERA (Weryfikacja w Sieci)
    if research.icebreaker and research.icebreaker.strip() not in ("Brak", "NULL", "None", ""):
        print(f"      🕵️ FACT CHECK (Internet): Weryfikuję aktualność: {research.icebreaker}")
        search_query = f"{company.name} {research.icebreaker} aktualne {current_year}"
        
        try:
            search_results = _run_async_safe(scraper.search(search_query))
            if search_results and len(search_results) > 10:
                fact_check_prompt = f"""Dziś jest {current_date_str}.
Icebreaker ze strony firmy {company.name}: "{research.icebreaker}"

Oto wyniki wyszukiwania w Google:
{search_results}

Czy ten temat/program/inicjatywa OFICJALNIE DZIAŁA w {current_year} roku w Polsce?
- Jeśli to program NFZ/rządowy/UE — sprawdź czy jest w aktualnym wykazie, czy nie został wycofany, zawieszony lub zastąpiony innym.
- Jeśli to inicjatywa/wydarzenie — sprawdź czy jest aktualna, nie historyczna.

Nadawca specjalizuje się w rozliczeniach NFZ — MUSI wiedzieć które programy działają. Wymienienie martwego programu jest NIEPROFESJONALNE.

Zwróć TYLKO słowo 'VALID' jeśli program/temat oficjalnie działa w {current_year}.
Zwróć 'INVALID' jeśli program zakończono, wstrzymano, zastąpiono lub jest stary."""
                
                fc_llm = create_llm(DEFAULT_MODEL, temperature=0.0)
                fc_resp = fc_llm.invoke([HumanMessage(content=fact_check_prompt)])
                # Bezpieczne wyciągnięcie tekstu — content może być str lub list
                fc_text = fc_resp.content if isinstance(fc_resp.content, str) else str(fc_resp.content)
                
                if "INVALID" in fc_text.upper():
                    print(f"      🚫 FACT CHECK OBLANY: Icebreaker nieaktualny! Uogólniam...")
                    # Zamiast 'Brak' — uogólniamy inteligentnie
                    generalize_prompt = f"""Icebreaker '{research.icebreaker}' okazał się NIEAKTUALNY (program/inicjatywa nie działa w {current_year}).
Firma: {company.name}. Branża firmy: {research.summary}.
Nadawca: {client_name} — oferuje: {client_value_prop[:200]}

Napisz JEDNO zdanie icebreakera które:
1. Uogólnia temat (np. zamiast 'program Profilaktyka 40+' → 'Państwa zaangażowanie w programy profilaktyczne')
2. Łączy to z ofertą nadawcy
3. Nie wspomina konkretnej nazwy programu/inicjatywy która już nie działa
4. Brzmi naturalnie i profesjonalnie

Zwróć TYLKO jedno zdanie, nic więcej."""
                    gen_llm = create_llm(DEFAULT_MODEL, temperature=0.3)
                    gen_resp = gen_llm.invoke([HumanMessage(content=generalize_prompt)])
                    gen_text = gen_resp.content if isinstance(gen_resp.content, str) else str(gen_resp.content)
                    research.icebreaker = gen_text.strip().strip('"').strip("'")
                    print(f"      🔄 UOGÓLNIONY ICEBREAKER: {research.icebreaker}")
                else:
                    print(f"      ✅ FACT CHECK ZDANY.")
        except Exception as e:
            logger.error(f"      ❌ Błąd w FactChecker (Internet): {e}")

    # 3. SCORING & SELECTION
    _raw_combined = list(set((research.contact_emails or []) + regex_emails))
    
    # Globalna blokada Freemaili (zwalczanie adresów wygenerowanych przez LLM)
    FREEMAILS = {
        'wp.pl', 'o2.pl', 'onet.pl', 'onet.eu', 'op.pl', 'interia.pl', 'interia.eu', 'interia.com',
        'poczta.fm', 'tlen.pl', 'gazeta.pl', 'go2.pl', 'vp.pl', 'spoko.pl', 'vip.interia.pl',
        'autograf.pl', 'int.pl', 'aqq.eu', 'poczta.onet.pl', 'poczta.wp.pl', 'pro.wp.pl',
        'o2.eu', 'buziaczek.pl', 'amorki.pl', 'lubie.to', 'poczta.interia.pl',
        'gmail.com', 'googlemail.com', 'hotmail.com', 'outlook.com', 'live.com', 
        'msn.com', 'windowslive.com', 'passport.com', 'outlook.eu', 'hotmail.co.uk',
        'yahoo.com', 'ymail.com', 'rocketmail.com', 'aol.com', 'aim.com',
        'icloud.com', 'me.com', 'mac.com', 'protonmail.com', 'proton.me', 'pm.me',
        'tutanota.com', 'tuta.io', 'mail.com', 'zoho.com', 'yandex.com', 'gmx.com'
    }
    
    # [DISABLED] Freemail blocking — zakomentowane bo małe placówki używają gmail.com jako firmowego
    # combined_emails = []
    # for email in _raw_combined:
    #     if not email or "@" not in email: continue
    #     domain_part = email.split('@')[1].lower().strip()
    #     if domain_part in FREEMAILS:
    #         print(f"      🚫 FREEMAIL KWARANTANNA: Odrzucono '{email}' (LLM Leak)")
    #         continue
    #     combined_emails.append(email.lower())
    combined_emails = [e.lower() for e in _raw_combined if e and "@" in e]
        
    def score_email(email):
        s = 0
        e = email.lower()
        local_part = e.split('@')[0] if '@' in e else e
        
        if mode == "JOB_HUNT":
            if any(x in e for x in ['kariera', 'jobs', 'rekrutacja', 'hr', 'people']): s += 20
            if any(x in e for x in ['cto', 'tech', 'engineering']): s += 25
            if any(x in e for x in ['ceo', 'founder']): s += 15
        else:
            # DECYDENCI — najwyższy priorytet
            if any(x in local_part for x in ['kierownik', 'dyrektor', 'manager', 'zarzad', 'prezes', 'wlasciciel']): s += 30
            if any(x in local_part for x in ['ceo', 'owner', 'founder']): s += 20
            # DOBRE OGOLNE — akceptowalne
            if any(x in local_part for x in ['biuro', 'info', 'hello', 'kontakt', 'office', 'sekretariat']): s += 15
            # BEZWARTOŚCIOWE SKRZYNKI FUNKCYJNE (użytkowe, nie do kontaktu) — kara
            if any(x in local_part for x in [
                'recepty', 'recepta', 'e-recepty', 'erecept',
                'laboratorium', 'lab', 'wyniki',
                'kadry', 'zus', 'pit', 'faktury', 'faktura',
                'newsletter', 'marketing', 'promo',
            ]): s -= 150
            # ZABRONIONE — compliance / HR
            if any(x in local_part for x in ['kariera', 'jobs', 'rekrutacja', 'iodo', 'rodo', 'dpo', 'inspektor']): s -= 200
            
        # Email imienny (jan.kowalski@) — bonus
        if '.' in local_part and len(local_part) > 5: s += 10
        
        # --- WALIDACJA ZGODNOŚCI DOMENY ---
        email_domain = e.split('@')[1] if '@' in e else ""
        target_domain = (company.domain or "").lower().replace("www.", "")
        target_root = target_domain.split('.')[-2] if len(target_domain.split('.')) >= 2 else target_domain
        
        if email_domain == target_domain:
            s += 100  # Dokładne trafienie w domenę firmy
        elif target_root and target_root in email_domain:
            s += 50   # Poddomeny lub pokrewne
        else:
            s -= 30   # Lekka kara za obcą domenę (gmail/wp jako firmowy = OK, ale niżej w rankingu)

        # MX check do sortowania
        if not verify_email_mx(e): s -= 200 
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
    
    debounce_is_down = False

    for candidate, score in scored:
        if score < -50: continue # Odrzucamy obce domeny poniżej progu i inbalidy

        print(f"      🛡️ Weryfikacja DeBounce dla: {candidate}...")
        status = verify_email_deep(candidate)  # ← This now uses Redis cache!

        if status == "API_DOWN":
            # DeBounce niedostępny — blokujemy wysyłkę, zostawiamy lead do retry
            debounce_is_down = True
            print(f"         🚨 DeBounce API niedostępny — wstrzymuję weryfikację!")
            logger.warning("[RESEARCHER] DeBounce API niedostępny — lead pozostaje PENDING do retry")
            # Alert email do operatora (max 1 na 4h)
            send_operator_alert(
                alert_type="debounce_down",
                subject="DeBounce API niedostępny — wysyłka wstrzymana",
                body=(
                    "DeBounce API zwróciło błąd (brak kredytów lub awaria serwera).\n\n"
                    "Silnik NEXUS automatycznie wstrzymał weryfikację maili.\n"
                    "Leady pozostają w statusie PENDING i zostaną przetworzone\n"
                    "gdy DeBounce znów będzie dostępny.\n\n"
                    "Działanie wymagane:\n"
                    "  1. Sprawdź stan konta DeBounce: https://debounce.io\n"
                    "  2. Doładuj kredyty jeśli wyczerpane\n"
                    "  3. Silnik wznowi wysyłkę automatycznie przy następnym cyklu\n\n"
                    "Żadne emaile nie zostały wysłane bez weryfikacji DeBounce."
                ),
            )
            break  # Nie sprawdzaj kolejnych — wszystkie odpadną tak samo

        elif status in ["OK", "RISKY"]:
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

    if debounce_is_down:
        # Lead zostaje jako NEW — zostanie ponownie przetworzony gdy DeBounce wróci
        # (scraping website jest cache'owany w Redis 14 dni — brak dodatkowego kosztu przy retry)
        lead.status = "NEW"
        lead.ai_confidence_score = 0
        session.commit()
        return  # Przerywamy — nie zapisuj błędnych danych

    if not final_email and scored:
        verification_note = "All emails failed verification."

    # 5. ZAPIS
    company.tech_stack = research.tech_stack
    company.decision_makers = research.decision_makers
    company.industry = research.target_audience
    company.pain_points = research.pain_points_or_opportunities
    company.last_scraped_at = datetime.now(PL_TZ)
    
    verified_name = (research.verified_contact_name or "").strip() or None

    lead.ai_analysis_summary = (
        f"MODE: {mode}\n"
        f"VERIFIED_CONTACT_NAME: {verified_name or 'NULL'}\n"
        f"ICEBREAKER: {research.icebreaker}\n"
        f"DATA_CURRENCY: {research.data_currency_analysis}\n"
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
