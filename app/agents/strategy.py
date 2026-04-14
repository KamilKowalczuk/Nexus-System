import os
import re
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Importy z Twojej aplikacji
from app.database import Client, SearchHistory, ClientAlignment
from app.schemas import StrategyOutput, SearchQuery
from app.memory_utils import load_used_queries
from app.model_factory import create_structured_llm, DEFAULT_MODEL

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strategy")


def generate_strategy(client: Client, raw_intent: str, campaign_id: int, session: Session | None = None) -> StrategyOutput:
    """
    Generuje UNIKALNE zapytania do Google Maps.
    Obsługuje dwa tryby: SALES (Szukanie klientów) oraz JOB_HUNT (Szukanie pracodawców).
    """

    # 1. ŁADUJEMY PAMIĘĆ
    used_queries = load_used_queries(campaign_id)
    used_queries_str = ", ".join(used_queries[-50:]) if used_queries else "BRAK"

    # 2. KONTEKST BRIEFU
    mode = getattr(client, "mode", "SALES")
    sender_name = client.name or ""
    sender_industry = client.industry or ""
    uvp = client.value_proposition or ""
    icp = client.ideal_customer_profile or ""
    constraints = client.negative_constraints or ""

    # 3. SEARCH HISTORY STATS (self-learning — które zapytania dają wyniki)
    search_stats_block = ""
    strategy_alignment_block = ""
    if session:
        try:
            # Top performing queries (yield rate)
            from sqlalchemy import func, desc
            stats = (
                session.query(
                    SearchHistory.query_text,
                    func.sum(SearchHistory.results_found).label("total_results"),
                    func.count(SearchHistory.id).label("times_used"),
                )
                .filter(SearchHistory.client_id == client.id)
                .group_by(SearchHistory.query_text)
                .order_by(desc("total_results"))
                .limit(15)
                .all()
            )
            if stats:
                top_queries = [f"  - \"{s.query_text}\" → {s.total_results} wyników ({s.times_used}x)" for s in stats[:10] if s.total_results > 0]
                zero_queries = [f"  - \"{s.query_text}\" → 0 wyników" for s in stats if s.total_results == 0]
                parts = []
                if top_queries:
                    parts.append("SKUTECZNE ZAPYTANIA (dawały wyniki):\n" + "\n".join(top_queries))
                if zero_queries:
                    parts.append("NIESKUTECZNE (0 wyników — unikaj podobnych):\n" + "\n".join(zero_queries[:5]))
                if parts:
                    search_stats_block = "\n=== 📊 STATYSTYKI HISTORYCZNE ===\n" + "\n".join(parts) + "\nWYCIĄGNIJ WNIOSKI: jakie synonimy/formaty działają, a jakie nie.\n"
                    logger.info(f"[STRATEGY] Search stats: {len(top_queries)} skutecznych, {len(zero_queries)} pustych")

            # Teacher alignment (strategy_guidelines)
            alignment = session.query(ClientAlignment).filter_by(client_id=client.id).first()
            if alignment and alignment.strategy_guidelines:
                strategy_alignment_block = (
                    f"\n=== 🧠 DYNAMICZNA WIEDZA KLIENTA (BEZWZGL. PRIORYTET — v{alignment.version}) ===\n"
                    f"{alignment.strategy_guidelines}\n"
                    f"=== KONIEC DYNAMICZNEJ WIEDZY ===\n"
                )
                logger.info(f"[STRATEGY] Teacher Alignment v{alignment.version} wstrzyknięty")
        except Exception as e:
            logger.debug(f"[STRATEGY] Stats/alignment niedostępne: {e}")

    if mode == "JOB_HUNT":
        system_prompt = f"""Jesteś łowcą ukrytych perełek rynku pracy. Generujesz zapytania do Google Maps, które odkryją firmy NIEDOSTĘPNE na portalach rekrutacyjnych.

=== PROFIL KANDYDATA ===
Imię: {sender_name}
Branża: {sender_industry}
Umiejętności: {uvp}
Wymarzone firmy: {icp}
Cel kampanii: {raw_intent}
Ograniczenia: {constraints or "brak"}

=== CZARNA LISTA (UŻYTE — nie powtarzaj) ===
{used_queries_str}

=== ZASADY GENEROWANIA ZAPYTAŃ ===

1. PRECYZJA GEOGRAFICZNA:
   - Google Maps daje max 20 wyników na ogólne miasto. Dlatego: dzielnice + POI.
   - "Software House near Rondo ONZ Warsaw" > "Software House Warszawa"
   - Miasta satelickie (Katowice, Łódź, Bielsko-Biała) = mniej konkurencji

2. DYWERSYFIKACJA SEMANTYCZNA:
   - Nie "Software House" x5. Zamiast tego: "Agencja Python", "SaaS Development", "AI Lab", "Fintech Startup", "Cloud Native Company"
   - Szukaj po technologiach: "React Agency", "Django Studio"

3. UKRYTY RYNEK PRACY:
   - "Series A Startup [Tech]" = firma z fundingiem = hiring mode
   - "[Tech] Scale-up" = faza wzrostu = potrzebują ludzi

4. WYKLUCZENIA:
   - NIGDY: "Biuro pracy", "Agencja rekrutacyjna" — szukamy bezpośrednich pracodawców

5. UNIKALNOŚĆ SEMANTYCZNA:
   - "Software House Kraków" ≈ "Kraków Software House" → to DUPLIKAT
   - Każde zapytanie musi różnić się BRANŻĄ lub LOKALIZACJĄ

Wygeneruj 5-8 precyzyjnych, RÓŻNORODNYCH zapytań. Format: czysty tekst do wpisania w Google Maps."""

    else:
        system_prompt = f"""Jesteś strategiem lead generation B2B. Generujesz zapytania do Google Maps.
{strategy_alignment_block}
=== NASZ KLIENT ===
Firma: {sender_name}
Branża: {sender_industry}
Co oferuje: {uvp}
Cel: {raw_intent}

=== KOGO SZUKAMY (ICP) ===
{icp}

=== OGRANICZENIA ===
{constraints or "brak"}

=== CZARNA LISTA (nie powtarzaj!) ===
{used_queries_str}
{search_stats_block}
=== ⚠️ KRYTYCZNA ZASADA: KRÓTKIE ZAPYTANIA! ⚠️ ===

Google Maps zwraca WIĘCEJ wyników na KRÓTKIE zapytania!
- ✅ "[synonim branżowy] [miasto]" → 30-50 wyników
- ❌ "[synonim branżowy] [pełny opis specjalizacji] [miasto]" → 1-3 wyniki!

KAŻDE zapytanie: MAKSYMALNIE 2-4 słowa! (synonim + miasto)

=== STRATEGIA ===

1. FORMAT ZAPYTANIA: [synonim branżowy] + [miasto z ICP]
    Każde zapytanie MAKSYMALNIE 2-4 słowa!
    Na podstawie ICP i branży nadawcy, SAM wymyśl synonimy branżowe dla firm docelowych.
    Np. jeśli szukamy przychodni: "przychodnia", "NZOZ", "centrum medyczne", "ośrodek zdrowia"
    Np. jeśli szukamy firm IT: "software house", "agencja IT", "studio programistyczne"
    Np. jeśli szukamy restauracji: "restauracja", "bistro", "catering"

2. RÓŻNICUJ SYNONIMY w ramach docelowych miast:
   Każdy synonim daje INNE wyniki w Google Maps!
   Wygeneruj MIN. 3-5 RÓŻNYCH synonimów branżowych na podstawie ICP.

3. GEO-TARGETING: WYKORZYSTAJ LOKALIZACJE Z ICP!
   Zidentyfikuj z bloku "KOGO SZUKAMY (ICP)" oraz "Cel" interesujący klienta obszar geograficzny (województwo, region, miasta).
   Wygeneruj zapytania TYLKO dla miast należących do tego obszaru docelowego!
   Rotuj miasta - od największych do małych miasteczek w tym regionie.

4. WYBÓR ŹRÓDŁA (source):
   - "maps" — DOMYŚLNIE (90% zapytań)
   - "search" — tylko jeśli ICP wymaga firm w 100% zdalnych/online bez adresu fizycznego.

5. UNIKALNOŚĆ: Nie powtarzaj czarnej listy.

Wygeneruj 8-10 KRÓTKICH zapytań (2-4 słowa każde!)."""

    print(f"🧠 STRATEGY [{mode}]: Analizuję historię... Generuję zapytania.")

    # Dynamiczny model z konfiguracji klienta
    model_name = getattr(client, "scout_model", None) or DEFAULT_MODEL
    structured_llm = create_structured_llm(model_name, StrategyOutput, temperature=0.7)
    logger.info(f"[STRATEGY] Model: {model_name}")

    result = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="Wygeneruj zapytania. Trzymaj się ICP i ograniczeń klienta dosłownie."),
    ])

    # 3. VALIDATION & DEDUPLICATION
    if result.search_queries:
        # Remove duplicates (case-insensitive + semantic)
        unique_queries = []
        seen_normalized = set()
        
        for sq in result.search_queries:
            # Handle both SearchQuery objects and plain strings (backward compat)
            if isinstance(sq, str):
                q_clean = sq.strip()
                source = "maps"
            else:
                q_clean = sq.query.strip()
                source = (sq.source or "maps").lower().strip()
                if source not in ("maps", "search"):
                    source = "maps"
            
            # Skip empty or too short
            if not q_clean or len(q_clean) < 5:
                logger.warning(f"⚠️ Skipping too short query: '{q_clean}'")
                continue
            
            # Check for placeholders
            if '[' in q_clean or '{' in q_clean:
                logger.warning(f"🚨 PLACEHOLDER DETECTED: '{q_clean}' - SKIPPING")
                continue
            
            # Normalize (lowercase + sorted words for semantic dedup)
            words = sorted(q_clean.lower().split())
            normalized = " ".join(words)
            
            # Check if semantically unique
            if normalized in seen_normalized:
                logger.warning(f"⚠️ SEMANTIC DUPLICATE: '{q_clean}' - SKIPPING")
                continue
            
            # Passed all checks
            unique_queries.append(SearchQuery(query=q_clean, source=source))
            seen_normalized.add(normalized)
        
        logger.info(f"✅ Generated {len(unique_queries)} unique queries (filtered from {len(result.search_queries)})")
        
        # Update result
        result.search_queries = unique_queries
        
        # NOTE: Queries are NOT saved to memory here anymore.
        # They will be saved by scout.py AFTER successful Apify execution.
        # This prevents "burning" queries that returned 0 results.
        
        if not unique_queries:
            logger.error(f"❌ No valid queries after validation - regeneration needed")
    
    return result
