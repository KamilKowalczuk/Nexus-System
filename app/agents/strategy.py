import os
import re
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv

# Importy z Twojej aplikacji
from app.database import Client
from app.schemas import StrategyOutput
from app.memory_utils import load_used_queries, save_used_queries
from app.model_factory import create_structured_llm, DEFAULT_MODEL

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("strategy")


def generate_strategy(client: Client, raw_intent: str, campaign_id: int) -> StrategyOutput:
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
        system_prompt = f"""Jesteś strategiem lead generation B2B. Twoje zapytania do Google Maps muszą trafiać jak snajper — DOKŁADNIE w profil idealnego klienta, nie obok.

=== NASZ KLIENT (w czyim imieniu szukamy) ===
Firma: {sender_name}
Branża: {sender_industry}
Co oferuje: {uvp}
Cel kampanii: {raw_intent}

=== KOGO SZUKAMY (ICP — Ideal Customer Profile) ===
{icp}

=== CZEGO NIE SZUKAMY (ograniczenia z briefu) ===
{constraints or "brak specjalnych ograniczeń"}

=== CZARNA LISTA (UŻYTE — nie powtarzaj) ===
{used_queries_str}

=== STRATEGIA GENEROWANIA ZAPYTAŃ ===

KLUCZOWA ZASADA: Czytaj ICP DOSŁOWNIE.
- Jeśli ICP mówi "małe firmy" / "do 10 pracowników" / "lokalne" → NIE szukaj sieci, korporacji, franczyz. Szukaj: "gabinet", "studio", "pracownia", "kancelaria", "warsztat".
- Jeśli ICP mówi "średnie firmy" / "50-200 pracowników" → szukaj: "hurtownia", "fabryka", "producent", "deweloper".
- Jeśli ICP mówi konkretną branżę → szukaj SYNONIMÓW tej branży (restauracja = bistro, gastrobar, pizzeria, sushi).

1. MIKRO-LOKALIZACJE (obowiązkowe dla dużych miast):
   - Google Maps ucina wyniki po ~20. Dlatego: dzielnice + POI.
   - "Klinika stomatologiczna near Rynek Główny Kraków" > "Dentysta Kraków"
   - Mniejsze miasta dają lepsze wyniki (mniej szumu)

2. SYNONIMÓW BIZNESOWE:
   - Nie powtarzaj tego samego słowa. Szukaj jak klienci szukają sami siebie.
   - "Biuro rachunkowe" = "Księgowość", "Doradztwo podatkowe", "Kancelaria podatkowa"
   - "Firma IT" = "Software House", "Agencja interaktywna", "Studio programistyczne"

3. KREATYWNE NISZE:
   - Kto MA PIENIĄDZE i potrzebuje usług {sender_industry}?
   - Branże w fazie wzrostu, po fundingu, przed transformacją cyfrową

4. UNIKALNOŚĆ:
   - "Restaurant Warsaw Mokotów" ≈ "Mokotów Restaurant Warsaw" → DUPLIKAT
   - Każde zapytanie: inna BRANŻA lub inna LOKALIZACJA

Wygeneruj 5-8 chirurgicznie precyzyjnych zapytań. Format: czysty tekst do Google Maps."""

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
        
        for q in result.search_queries:
            # Clean query
            q_clean = q.strip()
            
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
            unique_queries.append(q_clean)
            seen_normalized.add(normalized)
        
        logger.info(f"✅ Generated {len(unique_queries)} unique queries (filtered from {len(result.search_queries)})")
        
        # Update result
        result.search_queries = unique_queries
        
        # Save to memory
        if unique_queries:
            save_used_queries(campaign_id, unique_queries)
        else:
            logger.error(f"❌ No valid queries after validation - regeneration needed")
    
    return result
