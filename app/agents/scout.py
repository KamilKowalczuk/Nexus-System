import os
import asyncio
import logging
from typing import List, Dict, Any, Set, Optional
from urllib.parse import urlparse
from apify_client import ApifyClientAsync
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc, text
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# AI Imports
from langchain_core.messages import SystemMessage, HumanMessage

# Importy aplikacji
from app.database import GlobalCompany, Lead, SearchHistory, Campaign, Client
from app.schemas import StrategyOutput
from app.rodo_manager import is_domain_opted_out
from app.model_factory import create_llm, DEFAULT_MODEL
from app import stats_manager
from app import critical_monitor

# --- KONFIGURACJA ENTERPRISE ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scout")
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
# === BEZPIECZNIKI (FUSES) ===
BATCH_SIZE = 40             
SAFETY_LIMIT_LEADS = 20     
SAFETY_LIMIT_QUERIES = 4    
DUPLICATE_COOLDOWN_DAYS = 30 
GLOBAL_CONTACT_COOLDOWN = 30 

# DOSTĘPNE ŹRÓDŁA DANYCH (Actors)
ACTOR_MAPS = "compass/crawler-google-places"
ACTOR_SEARCH = "apify/google-search-scraper"

if not APIFY_TOKEN:
    logger.error("❌ CRITICAL: Brak APIFY_API_TOKEN. Scout jest martwy.")
    client = None
else:
    client = ApifyClientAsync(APIFY_TOKEN)

# --- MODEL DANYCH DLA AI GATEKEEPERA ---
class ValidatedDomain(BaseModel):
    domain: str = Field(..., description="Czysta domena, np. 'softwarehouse.com'")
    reason: str = Field(..., description="Krótkie uzasadnienie dlaczego pasuje do ICP")

class BatchValidationResult(BaseModel):
    valid_domains: List[ValidatedDomain] = Field(default_factory=list)

# --- LOGIKA BIZNESOWA ---

def _clean_domain(website_url: str) -> str | None:
    """Enterprise-grade domain sanitizer."""
    if not website_url: return None
    try:
        parsed = urlparse(website_url)
        domain = parsed.netloc or parsed.path 
        domain = domain.replace("www.", "").lower().strip()
        
        if "/" in domain: domain = domain.split("/")[0]

        blacklist = [
            "facebook.com", "instagram.com", "linkedin.com", "google.com", "youtube.com", "twitter.com", 
            "booksy.com", "znanylekarz.pl", "yelp.com", "researchgate.net", "wikipedia.org", "medium.com",
            "glassdoor.com", "indeed.com", "pracuj.pl", "nofluffjobs.com", "justjoin.it", "scholar.google.ca", 
            "scholar.google.com", "amazon.com", "allegro.pl", "olx.pl", "otomoto.pl", "booking.com", "tripadvisor.com",
            "f6s.com", "clutch.co", "goodfirms.co", "lekarzebezkolejki.pl", "gumtree.pl", "olx.pl", "sprzedajemy.pl", "gratka.pl", "autotrader.com", "cars.com", "znanylekarz.pl", "yelp.com", "tripadvisor.com", "glassdoor.com", "indeed.com", "pracuj.pl", "nofluffjobs.com", "justjoin.it", "scholar.google.ca", "scholar.google.com"
        ]
        
        if domain.endswith(".gov") or domain.endswith(".edu"): return None
        if domain in blacklist: return None
        if "." not in domain: return None

        return domain
    except Exception:
        return None

def _get_client_icp(session: Session, campaign_id: int) -> dict:
    """Pobiera pełny kontekst klienta z briefu — do filtracji AI i strategii."""
    campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not campaign.client:
        return {"icp": "General Business", "industry": "B2B", "mode": "SALES",
                "value_proposition": "", "negative_constraints": "", "strategy_prompt": ""}
    c = campaign.client
    return {
        "icp": c.ideal_customer_profile or "",
        "industry": c.industry or "",
        "mode": getattr(c, "mode", "SALES"),
        "value_proposition": c.value_proposition or "",
        "negative_constraints": c.negative_constraints or "",
        "strategy_prompt": campaign.strategy_prompt or "",
        "scout_model": getattr(c, "scout_model", None) or DEFAULT_MODEL,
    }

async def _ai_filter_batch(raw_items: List[Dict], client_data: Dict) -> List[str]:
    """
    AI GATEKEEPER v3: Zbalansowany filtr — przepuszcza rozsądne dopasowania,
    odrzuca oczywiste śmieci. Filozofia: lepiej mieć lead do zweryfikowania
    niż stracić potencjalnego klienta.
    """
    candidates = []
    for item in raw_items:
        url = item.get("website") or item.get("url")
        clean = _clean_domain(url)
        if clean:
            name = item.get("title") or item.get("title", "Unknown")
            category = item.get("categoryName") or "Web Search"
            # Dodaj dane o skali jeśli dostępne (Google Maps daje review count, rating)
            reviews = item.get("totalScore", "")
            review_count = item.get("reviewsCount", "")
            size_hint = ""
            if review_count:
                size_hint = f" | REVIEWS: {review_count}"
            elif reviews:
                size_hint = f" | RATING: {reviews}"
            candidates.append(f"- {clean} | {name} | {category}{size_hint}")

    if not candidates:
        return []

    candidates_str = "\n".join(candidates[:50])

    icp = client_data["icp"]
    industry = client_data["industry"]
    mode = client_data["mode"]
    constraints = client_data["negative_constraints"]

    # Budujemy sekcję twardych zakazów jeśli są zdefiniowane
    hard_block_section = ""
    if constraints and constraints.strip():
        hard_block_section = f"""
=== !! TWARDE ZAKAZY — BEZWZGLĘDNE !! ===
Pole poniżej może zawierać dwa typy ograniczeń: dotyczące TYPÓW FIRM (np. "nie szpitale", "nie korporacje") oraz dotyczące treści maili (np. "nie wspominaj o WordPress").
Tutaj stosujesz TYLKO zakazy dotyczące TYPÓW FIRM, branż, rozmiaru i lokalizacji.
Zakazy dotyczące treści maili → ignoruj (nie są Twoją odpowiedzialnością).

Zakazy firm/branż do zastosowania:
{constraints}

Jeśli masz wątpliwości czy firma pasuje do zakazu — ODRZUĆ.
"""

    system_prompt = f"""Jesteś filtrem jakości leadów B2B. Twoja robota: przepuścić firmy pasujące do profilu klienta i bezwzględnie blokować te niezgodne z zakazami.
{hard_block_section}
=== PROFIL KLIENTA ===
Branża klienta: {industry}
Kogo szuka (ICP): {icp}
Tryb: {mode} (SALES = szuka klientów do sprzedaży, JOB_HUNT = szuka pracodawców)

=== PRIORYTET DECYZYJNY ===
1. NAJPIERW sprawdź TWARDE ZAKAZY (sekcja powyżej). Jeśli firma pasuje do zakazu → ODRZUĆ. Koniec analizy dla tej firmy.
2. Czy KATEGORIA pasuje do ICP? Nie wymagaj perfekcji — pokrewna branża wystarczy.
3. Czy SKALA jest akceptowalna? Odrzucaj ewidentne korporacje i holdingi z wieloma oddziałami. Instytucje publiczne (urzędy, NFZ, ZUS) — zawsze odrzuć, chyba że ICP tego wymaga.
4. Czy to ewidentna konkurencja klienta? (DOKŁADNIE ta sama usługa = ODRZUĆ w trybie SALES).

=== KIEDY ODRZUCIĆ ===
- Pasuje do TWARDYCH ZAKAZÓW — zawsze, bez wyjątków
- Domena to znany portal/agregator/marketplace
- Ewidentna wielka korporacja lub instytucja publiczna (NFZ, ZUS, urząd, szpital publiczny)
- Oczywisty mismatch z ICP

=== KIEDY PRZEPUŚCIĆ ===
- Firma nie pasuje do żadnego zakazu i jest w obszarze ICP
- Małe i średnie firmy prywatne — priorytet
- Firma ma własną stronę WWW i wygląda profesjonalnie

=== KANDYDACI ===
{candidates_str}

Dla każdego kandydata: NAJPIERW sprawdź zakazy, potem ICP. Zatwierdź tylko firmy spełniające oba warunki."""

    scout_model = client_data.get("scout_model", DEFAULT_MODEL)
    gatekeeper_llm = create_llm(scout_model, temperature=0.0)
    gatekeeper = gatekeeper_llm.with_structured_output(BatchValidationResult)

    try:
        print(f"      🤖 [AI GATEKEEPER] Analizuję {len(candidates)} kandydatów...")
        result = await gatekeeper.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="Przeprowadź selekcję. Odrzuć oczywiste śmieci, przepuść rozsądne dopasowania. W razie wątpliwości — TAK."),
        ])

        valid_domains = [v.domain for v in result.valid_domains]
        print(f"      ✅ [AI GATEKEEPER] Przepuszczono: {len(valid_domains)}/{len(candidates)}")
        return valid_domains

    except Exception as e:
        logger.error(f"AI Filter Error: {e}")
        return [c.split("|")[0].replace("- ", "").strip() for c in candidates]

# --- FUNKCJE BAZODANOWE (Wrapper) ---

def _db_get_valid_queries(session: Session, campaign_id: int, raw_queries: List[str]) -> tuple[List[str], int]:
    campaign_obj = session.query(Campaign).filter(Campaign.id == campaign_id).first()
    client_id = campaign_obj.client_id if campaign_obj else None
    
    valid_queries = []
    print(f"\n🧠 [SCOUT MEMORY] Analizuję {len(raw_queries)} propozycji strategii...")

    for q in raw_queries:
        last_search = session.query(SearchHistory).filter(
            SearchHistory.client_id == client_id,
            SearchHistory.query_text == q,
            SearchHistory.searched_at > datetime.now(PL_TZ) - timedelta(days=DUPLICATE_COOLDOWN_DAYS)
        ).first()

        if last_search:
            print(f"   🚫 POMIJAM: '{q}' (Szukano: {last_search.searched_at.strftime('%Y-%m-%d')})")
        else:
            valid_queries.append(q)
            
    return valid_queries[:SAFETY_LIMIT_QUERIES], client_id

def _db_create_history_entry(session: Session, client_id: int, query: str) -> int:
    if not client_id: return None
    entry = SearchHistory(query_text=query, client_id=client_id, results_found=0)
    session.add(entry)
    session.commit()
    return entry.id

def _db_update_history_results(session: Session, entry_id: int, count: int):
    if not entry_id: return
    session.query(SearchHistory).filter(SearchHistory.id == entry_id).update({"results_found": count})
    session.commit()

def _db_process_scraped_items(session: Session, campaign_id: int, items: List[Dict], query: str, approved_domains: List[str]) -> int:
    """
    Wersja v2: Przyjmuje listę approved_domains z AI.
    """
    added_count = 0
    
    # 1. Filtrowanie po liście od AI
    # approved_domains są już po _clean_domain w funkcji AI, ale dla pewności:
    clean_approved = set(d.lower().strip() for d in approved_domains)

    if not clean_approved:
        return 0

    # 1b. FILTR BLACKLISTY RODO (domain hash) — przed jakimkolwiek zapisem do DB
    before_count = len(clean_approved)
    clean_approved = {
        d for d in clean_approved
        if not is_domain_opted_out(session, d)
    }
    blocked = before_count - len(clean_approved)
    if blocked > 0:
        logger.info(f"[SCOUT] Zablokowano {blocked} domen(y) z blacklisty RODO.")
        # STATS: blacklisted domains
        campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
        if campaign:
            stats_manager.increment_blacklisted(session, campaign.client_id, blocked)

    if not clean_approved:
        logger.info("[SCOUT] Wszystkie domeny na blackliście RODO — pomijam batch.")
        return 0

    # 2. Pobranie istniejących firm (Cache Bazy)
    existing_companies = session.query(GlobalCompany).filter(GlobalCompany.domain.in_(list(clean_approved))).all()
    existing_domains_map = {c.domain: c for c in existing_companies}
    
    new_companies_to_add = []
    
    # Mapowanie itemów na obiekty GlobalCompany
    for item in items:
        url = item.get("website") or item.get("url")
        d = _clean_domain(url)
        
        # KEY CHECK: Czy domena jest na liście zatwierdzonej przez AI?
        if not d or d not in clean_approved: continue
        
        if d not in existing_domains_map:
            title = item.get("title") or item.get("title", d)
            category = item.get("categoryName") or "Web Search"
            total_score = item.get("totalScore", 0) 
            
            quality_score = int(total_score * 20) if total_score else 60

            new_company = GlobalCompany(
                domain=d,
                name=title,
                pain_points=[f"Source: {category}", f"Query: {query}"],
                is_active=True,
                quality_score=quality_score
            )
            new_companies_to_add.append(new_company)
            existing_domains_map[d] = new_company 
    
    # Zapis nowych firm (flush = nadaje ID bez commitu, zostanie w jednej transakcji z leadami)
    if new_companies_to_add:
        session.add_all(new_companies_to_add)
        session.flush()  # ID przydzielone, ale transakcja otwarta
        for c in new_companies_to_add:
            existing_domains_map[c.domain] = c

    # 3. Przetwarzanie Leadów
    current_company_ids = [c.id for c in existing_domains_map.values()]
    
    leads_in_campaign = session.query(Lead.global_company_id).filter(
        Lead.campaign_id == campaign_id,
        Lead.global_company_id.in_(current_company_ids)
    ).all()
    ids_in_this_campaign = {l[0] for l in leads_in_campaign}
    
    new_leads_to_add = []
    
    for domain in clean_approved:
        if added_count >= SAFETY_LIMIT_LEADS: break
        
        company_obj = existing_domains_map.get(domain)
        if not company_obj: continue

        if company_obj.id in ids_in_this_campaign: continue

        last_contact = session.query(Lead).filter(
            Lead.global_company_id == company_obj.id,
            Lead.status == "SENT"
        ).order_by(desc(Lead.sent_at)).first()

        if last_contact and last_contact.sent_at:
            days_since = (datetime.now(PL_TZ) - last_contact.sent_at).days
            if days_since < GLOBAL_CONTACT_COOLDOWN:
                print(f"      ⏳ {domain}: KARENCJA ({days_since} dni). Skip.")
                continue

        new_lead = Lead(
            campaign_id=campaign_id,
            global_company_id=company_obj.id,
            status="NEW",
            ai_confidence_score=company_obj.quality_score or 50
        )
        new_leads_to_add.append(new_lead)
        ids_in_this_campaign.add(company_obj.id)
        added_count += 1

    if new_leads_to_add:
        session.add_all(new_leads_to_add)
        session.commit()
        
    return len(new_leads_to_add)


async def run_scout_async(session: Session, campaign_id: int, strategy: StrategyOutput) -> int:
    """
    Silnik Zwiadowczy v6.0 (AI Gatekeeper Enhanced).
    """
    if not client:
        print("❌ Scout Error: Klient Apify nie jest zainicjowany.")
        return 0

    # Pobieramy kontekst klienta RAZ na początku
    client_data = _get_client_icp(session, campaign_id)
    print(f"🕵️ [SCOUT] Kontekst AI: Szukam dla branży '{client_data['industry']}'")

    total_added = 0
    
    raw_queries = strategy.search_queries
    valid_queries, client_id = await asyncio.to_thread(_db_get_valid_queries, session, campaign_id, raw_queries)
    
    if not valid_queries:
        print("   💤 Scout: Brak nowych zapytań (wszystkie wykorzystane).")
        return 0

    print(f"🚀 [ASYNC SCOUT] Startuję zwiad dla: {valid_queries}")

    for query in valid_queries:
        if total_added >= SAFETY_LIMIT_LEADS:
            print(f"   🧨 LIMIT LEADOW OSIĄGNIĘTY. Stop.")
            break

        print(f"   📍 Wykonuję: '{query}'...")
        
        use_google_search = False
        if "remote" in query.lower() or "saas" in query.lower() or "startup" in query.lower() or "software" in query.lower():
            use_google_search = True
            print("      🌐 Tryb: GOOGLE SEARCH")
        else:
            print("      🗺️  Tryb: GOOGLE MAPS")

        history_id = await asyncio.to_thread(_db_create_history_entry, session, client_id, query)

        APIFY_TIMEOUT = 120  # max 2 minuty na jeden query — anti-hang

        items = []
        try:
            if not use_google_search:
                run_input = {
                    "searchStringsArray": [query],
                    "maxCrawledPlacesPerSearch": BATCH_SIZE,
                    "language": "pl",
                    "skipClosedPlaces": True,
                    "onlyWebsites": True,
                }
                run = await asyncio.wait_for(
                    client.actor(ACTOR_MAPS).call(run_input=run_input),
                    timeout=APIFY_TIMEOUT,
                )
            else:
                clean_query = query + " -site:linkedin.com -site:facebook.com -site:youtube.com"
                run_input = {
                    "queries": clean_query,
                    "resultsPerPage": BATCH_SIZE,
                    "countryCode": "pl",
                    "languageCode": "pl",
                }
                run = await asyncio.wait_for(
                    client.actor(ACTOR_SEARCH).call(run_input=run_input),
                    timeout=APIFY_TIMEOUT,
                )

            if run:
                dataset = client.dataset(run["defaultDatasetId"])
                dataset_items_page = await dataset.list_items()
                raw_items = dataset_items_page.items
                
                if use_google_search:
                    for ri in raw_items:
                        items.extend(ri.get("organicResults", []))
                else:
                    items = raw_items

            if not items:
                print("      ⚠️ Brak wyników w Apify.")
                continue

            await asyncio.to_thread(_db_update_history_results, session, history_id, len(items))
            print(f"      📥 Pobranno {len(items)} surowych wyników.")

            # --- AI GATEKEEPER STEP ---
            # Zamiast wrzucać wszystko, pytamy Gemini co jest wartościowe
            approved_domains = await _ai_filter_batch(items, client_data)
            
            # STATS: Scouting metryki
            stats_manager.increment_scanned(session, client_id, len(items))
            if approved_domains:
                stats_manager.increment_approved(session, client_id, len(approved_domains))
                stats_manager.increment_rejected(session, client_id, len(items) - len(approved_domains))
            else:
                stats_manager.increment_rejected(session, client_id, len(items))

            if not approved_domains:
                print("      🗑️ AI odrzuciło wszystkie wyniki jako nieistotne.")
                continue

            # --- PROCESS BATCH ---
            added_in_batch = await asyncio.to_thread(
                _db_process_scraped_items, 
                session, 
                campaign_id, 
                items, 
                query, 
                approved_domains # Przekazujemy przefiltrowaną listę
            )
            
            print(f"      💾 Zapisano {added_in_batch} unikalnych leadów (z {len(approved_domains)} zaakceptowanych).")
            total_added += added_in_batch

        except asyncio.TimeoutError:
            print(f"      ⏱️ [SCOUT] Timeout ({APIFY_TIMEOUT}s) — Apify nie odpowiedział dla '{query}'. Pomijam.")
            logger.warning(f"[SCOUT] Apify timeout dla query: '{query}'")
            critical_monitor.record_failure("apify")
        except Exception as e:
            err_str = str(e).lower()
            print(f"      ❌ Błąd w Async Scout: {e}")
            logger.error(f"[SCOUT] Błąd: {e}")
            if "unauthorized" in err_str or "invalid token" in err_str or "401" in err_str:
                # Nieprawidłowy klucz API → natychmiastowy stop
                critical_monitor.trigger_stop(
                    api_name="apify",
                    reason=f"Apify API zwróciło błąd autoryzacji — sprawdź APIFY_API_KEY w .env.",
                    consecutive=1,
                )
            elif "payment" in err_str or "402" in err_str or "insufficient" in err_str:
                critical_monitor.trigger_stop(
                    api_name="apify",
                    reason="Apify API zwróciło błąd płatności (HTTP 402) — wyczerpane środki.",
                    consecutive=1,
                )
            else:
                critical_monitor.record_failure("apify")
        else:
            critical_monitor.record_success("apify")

    print(f"🏁 [SCOUT] Koniec tury. Wynik: {total_added}/{SAFETY_LIMIT_LEADS}")
    return total_added