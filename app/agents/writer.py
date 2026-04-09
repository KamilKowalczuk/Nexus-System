import os
import hmac
import hashlib
import base64
import logging
import re
import random
from datetime import datetime
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv

from app.database import Lead, Client, GlobalCompany
from app.schemas import EmailDraft, AuditResult
from app.rodo_manager import generate_rodo_clause
from app import stats_manager
from app.model_factory import create_llm, create_structured_llm, DEFAULT_MODEL

_OPTOUT_HMAC_SECRET = os.getenv("OPTOUT_HMAC_SECRET", "").encode("utf-8")
_SITE_URL = os.getenv("SITE_URL", "https://nexusagent.pl")

# =====================================================================
# WRITER ENGINE v5: SYSTEM RÓŻNORODNOŚCI MAILI
# =====================================================================

# Mapowanie nazw tonów z briefu (brief_sync) na klucze wewnętrzne
_TONE_KEY_MAP: dict[str, str] = {
    "Formalny / Korporacyjny": "formal",
    "Profesjonalny / Partnerski": "professional",
    "Bezpośredni / Konkretny": "direct",
    "Techniczny / Ekspercki": "technical",
    "formal": "formal",
    "professional": "professional",
    "direct": "direct",
    "technical": "technical",
}

# Profile tonów: persona (M/F), parametry LLM
_TONE_PROFILES: dict[str, dict] = {
    "professional": {
        "temperature": 0.75, "top_p": 0.85, "top_k": 40,
        "persona_m": (
            "Jesteś doświadczonym Business Development Managerem z 12-letnim stażem w B2B. "
            "Twoja siła: brzmisz jak partner biznesowy, nie jak sprzedawca. Piszesz pewnie, "
            "ale bez arogancji — jak kolega z branży, który dzieli się obserwacją.\n\n"
            'WAŻNE: Piszesz w RODZAJU MĘSKIM. Zawsze: "widziałem", "zauważyłem", '
            '"zastanawiałem się", "pracowałem", "rozmawiałem".'
        ),
        "persona_f": (
            "Jesteś doświadczoną Business Development Managerką z 12-letnim stażem w B2B. "
            "Twoja siła: brzmisz jak partnerka biznesowa, nie jak sprzedawczyni. Piszesz pewnie, "
            "ale bez arogancji — jak koleżanka z branży, która dzieli się obserwacją.\n\n"
            'WAŻNE: Piszesz w RODZAJU ŻEŃSKIM. Zawsze: "widziałam", "zauważyłam", '
            '"zastanawiałam się", "pracowałam", "rozmawiałam". NIGDY nie używaj rodzaju męskiego.'
        ),
    },
    "formal": {
        "temperature": 0.60, "top_p": 0.80, "top_k": 35,
        "persona_m": (
            "Jesteś Senior Consultantem z wieloletnią praktyką doradczą. Piszesz oficjalnie, "
            "z dystansem i szacunkiem — jak korespondencja z dużej firmy doradczej. "
            'Zwracasz się per "Państwo", utrzymujesz formalny rejestr języka.\n\n'
            'WAŻNE: Piszesz w RODZAJU MĘSKIM. Zawsze: "zwróciłem uwagę", '
            '"przeprowadziłem analizę". NIE używaj "pozwolę sobie" (zakazany zwrot AI).'
        ),
        "persona_f": (
            "Jesteś Senior Consultantką z wieloletnią praktyką doradczą. Piszesz oficjalnie, "
            "z dystansem i szacunkiem — jak korespondencja z dużej firmy doradczej. "
            'Zwracasz się per "Państwo", utrzymujesz formalny rejestr języka.\n\n'
            'WAŻNE: Piszesz w RODZAJU ŻEŃSKIM. Zawsze: "zwróciłam uwagę", '
            '"przeprowadziłam analizę". NIE używaj "pozwolę sobie" (zakazany zwrot AI).'
        ),
    },
    "direct": {
        "temperature": 0.65, "top_p": 0.80, "top_k": 35,
        "persona_m": (
            "Jesteś praktykiem-przedsiębiorcą. Zero bull***t approach. Piszesz ultrakrótko — "
            "każde słowo waży. Bez ozdobników, bez wstępów, bez grzeczności ponad minimum. "
            "Idziesz prosto do sedna.\n\n"
            'WAŻNE: Piszesz w RODZAJU MĘSKIM. Zawsze: "widziałem", "sprawdziłem", "szukam".'
        ),
        "persona_f": (
            "Jesteś praktyczką-przedsiębiorczynią. Zero bull***t approach. Piszesz ultrakrótko — "
            "każde słowo waży. Bez ozdobników, bez wstępów, bez grzeczności ponad minimum. "
            "Idziesz prosto do sedna.\n\n"
            'WAŻNE: Piszesz w RODZAJU ŻEŃSKIM. Zawsze: "widziałam", "sprawdziłam", "szukam".'
        ),
    },
    "technical": {
        "temperature": 0.55, "top_p": 0.75, "top_k": 30,
        "persona_m": (
            "Jesteś inżynierem/analitykiem z głęboką wiedzą branżową. Myślisz danymi i procesami. "
            "Piszesz rzeczowo, z terminologią branżową — jak ekspert do eksperta. "
            "Powołujesz się WYŁĄCZNIE na fakty z danych, nigdy nie zmyślasz metryk.\n\n"
            'WAŻNE: Piszesz w RODZAJU MĘSKIM. Zawsze: "przeanalizowałem", "zidentyfikowałem", "zmapowałem".'
        ),
        "persona_f": (
            "Jesteś inżynierką/analityczką z głęboką wiedzą branżową. Myślisz danymi i procesami. "
            "Piszesz rzeczowo, z terminologią branżową — jak ekspertka do eksperta. "
            "Powołujesz się WYŁĄCZNIE na fakty z danych, nigdy nie zmyślasz metryk.\n\n"
            'WAŻNE: Piszesz w RODZAJU ŻEŃSKIM. Zawsze: "przeanalizowałam", "zidentyfikowałam", "zmapowałam".'
        ),
    },
}

# 6 architektur otwarcia cold maila (SALES step==1)
_OPENING_STRATEGIES_COLD: list[dict] = [
    {
        "id": "diagnostic_question",
        "name": "Pytanie Diagnostyczne",
        "instruction": (
            '3. Pytanie prowadzące — zacznij od pytania o konkretny proces/wyzwanie u odbiorcy, '
            'potem daj 1 zdanie kontekstu dlaczego pytasz.\n'
            '   Struktura: "Jak wygląda u Państwa [proces z danych]? Pytam, bo [kontekst z doświadczenia]."\n'
            '   WAŻNE: Pytanie MUSI dotyczyć aspektu widocznego w danych odbiorcy.'
        ),
    },
    {
        "id": "micro_observation",
        "name": "Mikro-Obserwacja",
        "instruction": (
            '3. Mikro-obserwacja — opisz JEDEN konkretny fakt ze strony odbiorcy i JEDNĄ implikację '
            'łączącą się z ofertą nadawcy.\n'
            '   Struktura: "[Fakt ze strony]. W podobnych strukturach to zwykle sygnalizuje [implikacja]."\n'
            '   WAŻNE: Fakt MUSI być z danych researchu, implikacja z doświadczenia nadawcy.'
        ),
    },
    {
        "id": "inverted_perspective",
        "name": "Odwrócona Perspektywa",
        "instruction": (
            '3. Odwrócona perspektywa — pokaż kontrast między dwoma podejściami do problemu '
            'w branży odbiorcy. Nie mów które lepsze — zapytaj jak oni to robią.\n'
            '   Struktura: "Firmy w [segment] podchodzą do [temat] na dwa sposoby: [A] lub [B]. '
            'Ciekawi mnie, jak to wygląda u Państwa."\n'
            '   WAŻNE: Oba podejścia muszą być realistyczne.'
        ),
    },
    {
        "id": "pain_point_bridge",
        "name": "Punkt Bólu z Danych",
        "instruction": (
            '3. Most od pain pointu — weź konkretny pain point z researchu i połącz '
            'z jednym zdaniem kontekstu. Nie obiecuj rozwiązania.\n'
            '   Struktura: "[Pain point z danych]. Z naszych obserwacji — to area, '
            'która przy [skala] zaczyna wymagać uwagi."\n'
            '   WAŻNE: Pain point MUSI być z sekcji Możliwe potrzeby. Zero wymysłów.'
        ),
    },
    {
        "id": "market_signal",
        "name": "Sygnał Rynkowy",
        "instruction": (
            '3. Sygnał rynkowy — opisz trend w segmencie odbiorcy i zapytaj '
            'czy to temat na ich agendzie.\n'
            '   Struktura: "Obserwujemy, że [segment] coraz częściej weryfikuje [temat]. '
            'Ciekawi mnie, czy to temat, na który zwracacie uwagę."\n'
            '   WAŻNE: Trend musi logicznie wynikać z danych o branży odbiorcy.'
        ),
    },
    {
        "id": "intellectual_provocation",
        "name": "Prowokacja Intelektualna",
        "instruction": (
            '3. Prowokacja intelektualna — postaw lekko kontrowersyjną tezę '
            'dotyczącą branży i zapytaj o ich zdanie.\n'
            '   Struktura: "Pojawia się teza, że [obserwacja o branży]. '
            'Ciekawi mnie Państwa perspektywa — jak to wygląda od wewnątrz?"\n'
            '   WAŻNE: Teza musi być merytoryczna i powiązana z ofertą nadawcy.'
        ),
    },
]

# 4 architektury follow-up (SALES step > 1)
_OPENING_STRATEGIES_FOLLOWUP: list[dict] = [
    {
        "id": "new_angle",
        "name": "Nowy Kąt",
        "instruction": (
            '2-3. Nowy argument — wróć z INNYM aspektem problemu niż wcześniej. '
            'Dodaj jedną nową obserwację.\n'
            '   Struktura: "{_wracam} z jedną myślą — {_zastawialem} nad [NOWY aspekt] i [obserwacja]."\n'
            '   WAŻNE: NIE powtarzaj argumentów z poprzednich maili.'
        ),
    },
    {
        "id": "perspective_shift",
        "name": "Zmiana Perspektywy",
        "instruction": (
            '2-3. Zmiana perspektywy — pokaż problem z innej strony niż wcześniej. '
            'Np. jeśli wcześniej o procesach, teraz o zespole.\n'
            '   Struktura: "Patrząc na to z innej strony — [nowa perspektywa na temat]."\n'
            '   WAŻNE: Musi być widoczna jasna różnica kąta patrzenia vs. poprzedni mail.'
        ),
    },
    {
        "id": "trend_reference",
        "name": "Odwołanie do Trendu",
        "instruction": (
            '2-3. Odwołanie do trendu — nawiąż do zmiany rynkowej lub technologicznej '
            'w branży odbiorcy.\n'
            '   Struktura: "{_wracam} do tematu z kontekstem [trend]. '
            'Zaczynamy obserwować wpływ na [aspekt]."\n'
            '   WAŻNE: Trend MUSI być powiązany z branżą odbiorcy i ofertą nadawcy.'
        ),
    },
    {
        "id": "deepening_question",
        "name": "Pytanie Pogłębiające",
        "instruction": (
            '2-3. Pytanie pogłębiające — zadaj INNE pytanie niż wcześniej, '
            'bardziej szczegółowe i bliższe konkretnemu procesowi.\n'
            '   Struktura: "{_zastawialem} nad jedną rzeczą — [konkretne pytanie o proces]?"\n'
            '   WAŻNE: Pytanie musi być bardziej precyzyjne niż w pierwszym mailu.'
        ),
    },
]


# --- PULA PRZYKŁADÓW FEW-SHOT (3 per ton, indeksowane kluczem tonu) ---
_FEW_SHOT_POOL: dict[str, list[dict]] = {
    "professional": [
        {
            "label": "z icebreakerem, partnerski",
            "subject": "automatyzacja procesów",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_widzialem} że rozbudowujecie zespół sprzedaży — trzy nowe oferty "
                "na LinkedIn w tym miesiącu. To zwykle moment, kiedy ręczne prowadzenie "
                "pipeline'u zaczyna hamować skalowanie.</p>"
                "<p>Pracując z firmami o podobnej dynamice wzrostu, widzieliśmy wyraźny "
                "wzorzec — automatyzacja dopływu leadów eliminuje bottleneck po stronie "
                "handlowców.</p>"
                "<p>Czy to temat, który jest teraz na Waszej agendzie?</p>"
            ),
        },
        {
            "label": "bez icebrakera, obserwacja branżowa",
            "subject": "kwestia segmentacji",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Analizując rynek firm technologicznych z Waszego segmentu, zwróciło "
                "moją uwagę Wasze pozycjonowanie w obszarze ERP.</p>"
                "<p>Firmy o zbliżonym profilu coraz częściej sygnalizują, że manualny "
                "prospecting pochłania czas, który mógłby iść w rozwój produktu. "
                "Ciekawi mnie, czy to obserwacja bliska też Waszej codzienności?</p>"
            ),
        },
        {
            "label": "follow-up, nowy argument",
            "subject": "Re: kwestia segmentacji",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_wracam} z jedną myślą — {_zastawialem} nad rynkiem ERP i okazało "
                "się, że największym wyzwaniem nie bywa brak danych, a brak ich selekcji.</p>"
                "<p>Chętnie opowiem przy krótkiej rozmowie, jak podchodzimy do tego "
                "tematu. Czy to coś, o czym warto porozmawiać?</p>"
            ),
        },
    ],
    "formal": [
        {
            "label": "z icebreakerem, formalny",
            "subject": "kwestia procesów rekrutacyjnych",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Zwróciłem uwagę na intensywną rekrutację w Państwa organizacji — "
                "kilka otwartych procesów w obszarze IT w ostatnich tygodniach. Skala "
                "zatrudnień na tym poziomie generuje zazwyczaj istotne wyzwania "
                "administracyjne.</p>"
                "<p>Prowadząc analizę porównawczą w tym segmencie, zidentyfikowaliśmy "
                "powtarzalny wzorzec w obszarze automatyzacji tych procesów. Czy byliby "
                "Państwo otwarci na krótką wymianę obserwacji?</p>"
            ),
        },
        {
            "label": "bez icebrakera, analiza",
            "subject": "pytanie odnośnie infrastruktury",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Analizując podmioty o zbliżonym profilu działalności w Państwa "
                "segmencie rynku, zwróciłem uwagę na Państwa pozycjonowanie w obszarze "
                "usług profesjonalnych.</p>"
                "<p>Według naszych obserwacji, organizacje o tej strukturze coraz "
                "częściej raportują potrzebę weryfikacji procesów w zakresie pozyskiwania "
                "nowych kontraktów. Czy to obszar, który jest obecnie przedmiotem "
                "Państwa uwagi?</p>"
            ),
        },
        {
            "label": "follow-up, formalny",
            "subject": "Re: pytanie odnośnie infrastruktury",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Nawiązując do poprzedniej korespondencji — {_zastawialem} nad "
                "dodatkowym aspektem. Z perspektywy naszej praktyki, kluczowym elementem "
                "bywa nie sam proces, a jego skalowalność przy wzroście obciążenia.</p>"
                "<p>Byliby Państwo skłonni poświęcić 15 minut na krótką rozmowę "
                "w tym temacie?</p>"
            ),
        },
    ],
    "direct": [
        {
            "label": "z icebreakerem, bezpośredni",
            "subject": "szybkie pytanie",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_widzialem} nowe oferty pracy u Was. Rosnący zespół = rosnący "
                "chaos w procesach. Standardowa pułapka.</p>"
                "<p>Macie to ogarnięte, czy szukacie sposobu na usprawnienie?</p>"
            ),
        },
        {
            "label": "bez icebrakera, bezpośredni",
            "subject": "jeden temat",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Firmy z Waszego segmentu tracą średnio kilkanaście godzin tygodniowo "
                "na manualny prospecting. To czas, który mógłby iść w domykanie dealów.</p>"
                "<p>Weryfikujecie ten obszar?</p>"
            ),
        },
        {
            "label": "follow-up, bezpośredni",
            "subject": "Re: jeden temat",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_wracam} krótko. Jeden dodatkowy kontekst — firmy o Waszym profilu, "
                "z którymi rozmawialiśmy, najczęściej wskazują na selekcję leadów "
                "jako bottleneck nr 1.</p>"
                "<p>Warto porozmawiać?</p>"
            ),
        },
    ],
    "technical": [
        {
            "label": "z icebreakerem, techniczny",
            "subject": "integracja pipeline'u",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_widzialem} że pracujecie na stacku obejmującym systemy ERP. "
                "Przy tej architekturze, integracja danych prospectingowych z CRM-em "
                "staje się wąskim gardłem — szczególnie przy wolumenie powyżej "
                "50 leadów dziennie.</p>"
                "<p>Czy walidacja danych wejściowych do Waszego pipeline'u to temat, "
                "który obecnie analizujecie?</p>"
            ),
        },
        {
            "label": "bez icebrakera, techniczny",
            "subject": "architektura procesu",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Mapując procesy w firmach z segmentu usług technologicznych, "
                "identyfikujemy powtarzalny wzorzec — manualna kwalifikacja leadów "
                "przy skali 30+ kontaktów dziennie generuje error rate na poziomie, "
                "który wpływa na conversion rate dalszych etapów.</p>"
                "<p>Czy monitorujecie ten wskaźnik w Państwa procesie?</p>"
            ),
        },
        {
            "label": "follow-up, techniczny",
            "subject": "Re: architektura procesu",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_wracam} z dodatkowym punktem danych — {_zastawialem} nad metryką "
                "time-to-first-contact w Waszym segmencie. Z naszych benchmarków wynika, "
                "że skrócenie tego czasu o 40%% koreluje z wyraźnym wzrostem "
                "response rate.</p>"
                "<p>Czy mierzycie ten parametr u siebie?</p>"
            ),
        },
    ],
}


# =====================================================================
# HELPER FUNCTIONS — WRITER ENGINE v5
# =====================================================================

def _resolve_tone_key(tone_of_voice: str | None) -> str:
    """Rozwiązuje tone_of_voice z briefu klienta na klucz wewnętrzny."""
    if not tone_of_voice or not tone_of_voice.strip():
        return "professional"
    return _TONE_KEY_MAP.get(tone_of_voice.strip(), "professional")


def _build_persona(tone_key: str, sender_gender: str) -> str:
    """Buduje blok persony dopasowany do tonu i płci sendera."""
    profile = _TONE_PROFILES.get(tone_key, _TONE_PROFILES["professional"])
    gender_key = "persona_f" if sender_gender == "F" else "persona_m"
    return profile[gender_key]


def _select_opening_strategy(step: int, previous_emails: list | None) -> dict:
    """
    Losuje architekturę otwarcia z puli odpowiedniej dla stepu.
    Cold (step==1): 6 architektur. Follow-up (step>1): 4 architektury.
    """
    pool = list(_OPENING_STRATEGIES_FOLLOWUP) if step > 1 else list(_OPENING_STRATEGIES_COLD)
    return random.choice(pool)


def _select_few_shots(tone_key: str, sender_gender: str, count: int = 2) -> str:
    """
    Losuje przykłady few-shot z puli danego tonu.
    Formatuje formy gramatyczne (M/F) w treści przykładów.
    """
    pool = _FEW_SHOT_POOL.get(tone_key, _FEW_SHOT_POOL["professional"])
    selected = random.sample(pool, min(count, len(pool)))

    if sender_gender == "F":
        forms = {
            "{_widzialem}": "Widziałam",
            "{_zauwazyl}": "Zauważyłam",
            "{_zastawialem}": "Zastanawiałam się",
            "{_wracam}": "Wracam",
        }
    else:
        forms = {
            "{_widzialem}": "Widziałem",
            "{_zauwazyl}": "Zauważyłem",
            "{_zastawialem}": "Zastanawiałem się",
            "{_wracam}": "Wracam",
        }

    examples_text = "=== PRZYKŁADY DOBREGO STYLU ===\n\n"
    for i, ex in enumerate(selected, 1):
        body = ex["body"]
        for placeholder, val in forms.items():
            body = body.replace(placeholder, val)
        examples_text += f"Przykład {i} ({ex['label']}):\nSubject: {ex['subject']}\nBody:\n{body}\n\n"

    return examples_text


def _build_optout_url(email: str, base_url: str) -> str:
    """
    Buduje podpisany HMAC link opt-out.

    Format: {SITE_URL}/optout?t={hmac}&e={base64_email}

    Bezpieczeństwo:
    - HMAC-SHA256(secret, email) — nikt bez znajomości sekretu nie może wygenerować
      prawidłowego tokenu dla obcego emaila.
    - base64(email) — nie jest sekretem, tylko wygodnym encodingiem dla URL.
    - Token jest bezterminowy (walidacja po stronie endpointu może sprawdzić
      czy email jest już na blackliście = idempotentne).

    Returns:
        Pełny URL opt-out lub base_url jeśli brak konfiguracji.
    """
    if not email or not _OPTOUT_HMAC_SECRET:
        return base_url or "#"

    token = hmac.new(_OPTOUT_HMAC_SECRET, email.lower().strip().encode("utf-8"), hashlib.sha256).hexdigest()
    encoded_email = base64.urlsafe_b64encode(email.lower().strip().encode("utf-8")).decode("ascii")
    return f"{_SITE_URL}/optout?t={token}&e={encoded_email}"

# Konfiguracja loggera
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("writer")

load_dotenv()

# --- DETEKCJA PŁCI NA PODSTAWIE IMIENIA ---
# Polskie imiona męskie kończące się na -a (wyjątki od reguły)
_MALE_NAMES_ENDING_A = {
    "kuba", "barnaba", "bonawentura", "kosma", "dyzma", "jarema",
    "sasza", "beniamina", "boryna", "juda", "saba", "luca",
}

def _detect_gender(sender_name: str | None) -> str:
    """
    Wykrywa płeć na podstawie polskiego imienia.
    Returns: 'F' (kobieta), 'M' (mężczyzna)
    """
    if not sender_name:
        return "M"  # Default
    
    first_name = sender_name.strip().split()[0].lower()
    
    # Wyjątki — męskie imiona kończące się na -a
    if first_name in _MALE_NAMES_ENDING_A:
        return "M"
    
    # Reguła ogólna: polskie imiona żeńskie kończą się na -a
    if first_name.endswith("a"):
        return "F"
     
    return "M"

# --- SAFETY NET: HTML VALIDATOR ---
def _sanitize_and_validate_html(html_content: str) -> str:
    """
    Naprawia i czyści HTML wygenerowany przez AI.
    Chroni przed rozsypaniem się maila w Outlooku.
    """
    if not html_content:
        return ""

    # 1. Usuwanie niebezpiecznych tagów
    forbidden_tags = [r'<script.*?>.*?</script>', r'<iframe.*?>.*?</iframe>', r'<object.*?>.*?</object>', r'<style.*?>.*?</style>']
    clean_html = html_content
    for tag in forbidden_tags:
        clean_html = re.sub(tag, '', clean_html, flags=re.DOTALL | re.IGNORECASE)

    # 2. Sprawdzenie balansu tagów
    tags_to_check = ['div', 'p', 'b', 'strong', 'i', 'em', 'ul', 'li']
    
    for tag in tags_to_check:
        open_count = len(re.findall(f"<{tag}[^>]*>", clean_html, re.IGNORECASE))
        close_count = len(re.findall(f"</{tag}>", clean_html, re.IGNORECASE))
        
        if open_count > close_count:
            missing = open_count - close_count
            clean_html += f"</{tag}>" * missing

    # 3. Usuwanie wielokrotnych <br>
    clean_html = re.sub(r'(<br\s*/?>){3,}', '<br><br>', clean_html)
    
    return clean_html.strip()


def _parse_research_summary(summary: str) -> dict:
    """
    Parsuje ai_analysis_summary zapisane przez researcher.py.
    Zwraca słownik z kluczami: verified_contact_name, icebreaker, summary,
    key_products, pain_points.
    """
    result = {
        "verified_contact_name": None,
        "icebreaker": "",
        "summary": "",
        "key_products": "",
        "pain_points": "",
    }
    if not summary:
        return result

    for line in summary.splitlines():
        if ": " not in line:
            continue
        key, _, val = line.partition(": ")
        key = key.strip()
        val = val.strip()
        if key == "VERIFIED_CONTACT_NAME":
            result["verified_contact_name"] = None if val in ("NULL", "", "None") else val
        elif key == "ICEBREAKER":
            result["icebreaker"] = val if val not in ("Brak", "NULL", "") else ""
        elif key == "SUMMARY":
            result["summary"] = val
        elif key == "KEY_PRODUCTS":
            result["key_products"] = val
        elif key == "PAIN_POINTS":
            result["pain_points"] = val

    return result


def _resolve_greeting(verified_contact_name: str | None) -> str | None:
    """
    Zwraca imię do powitania LUB None (= ogólne "Dzień dobry,").

    Reguły:
    - Jedyne źródło: verified_contact_name z researchu (sekcja Zespół + pasujący email).
    - Email prefix, zgadywanie, nazwy firm → NIGDY.
    - Jeśli brak → None → writer użyje "Dzień dobry,".
    """
    if not verified_contact_name or verified_contact_name in ("NULL", "None", "Brak"):
        logger.info("   ℹ️ Brak zweryfikowanego imienia → powitanie: 'Dzień dobry,'")
        return None

    name = verified_contact_name.strip()
    if len(name) < 3 or len(name) > 25:
        return None

    logger.info(f"   ✅ Zweryfikowane imię z sekcji Zespół: {name}")
    return name



def _detect_hallucination_markers(text: str) -> list:
    """Detektuje znaki halucynacji (placeholders, niespójności)."""
    markers = []
    
    # CRITICAL: Placeholder detection
    if re.search(r'\[.*?\]', text):
        markers.append("placeholder_detected")
        logger.error("   🚨 PLACEHOLDER FOUND - REGENERATING")
    
    if re.search(r'\{.*?\}', text):
        markers.append("curly_placeholder_detected")
        logger.error("   🚨 CURLY PLACEHOLDER FOUND - REGENERATING")
    
    # Generic corporate speak + AI-isms
    generic_phrases = [
        r'mamy przyjemność',
        r'wychodzimy naprzeciw',
        r'kompleksowe rozwiązania',
        r'w dzisiejszych czasach',
        r'transformacja cyfrowa',
        r'innowacyjne podejście',
        r'z przyjemnością',
        r'pozwolę sobie',
        r'holistyczne podejście',
        r'strategiczne partnerstwo',
        r'wartość dodana',
        r'wymiana myśli',
        r'wzajemne korzyści',
        r'dynamiczny rozwój',
        r'lider w branży',
        r'umówić się na rozmowę',
        r'chciałbym zaproponować',
        r'pragnę przedstawić',
        r'zwracam się z',
        r'mam nadzieję że ten mail',
    ]
    
    for phrase in generic_phrases:
        if re.search(phrase, text, re.IGNORECASE):
            markers.append(f"generic_phrase: {phrase}")
    
    # Repeated patterns
    words = text.split()
    if len(words) > 10:
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
        
        if max(word_freq.values()) > 5:
            markers.append("word_repetition_detected")
    
    return markers


def _validate_against_data(email_body: str, company_data: dict, client_data: dict) -> dict:
    """Sprawdza czy mail nie halucynuje."""
    validation_result = {
        "is_hallucinating": False,
        "violations": [],
        "confidence_score": 100
    }
    
    # Hallucination markers
    hallucination_markers = _detect_hallucination_markers(email_body)
    if hallucination_markers:
        validation_result["is_hallucinating"] = True
        validation_result["violations"].extend(hallucination_markers)
        validation_result["confidence_score"] -= 50
    
    return validation_result

# -------------------------------------------

def generate_email(session: Session, lead_id: int):
    """
    Wrapper synchroniczny.
    """
    _generate_email_sync(session, lead_id)

def _generate_email_sync(session: Session, lead_id: int):
    """
    MASTER PROCESS: Generowanie maila.
    """
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead or not lead.campaign or not lead.campaign.client:
        logger.error(f"❌ Błąd danych leada ID {lead_id}.")
        return

    client = lead.campaign.client
    company = lead.company
    
    mode = getattr(client, "mode", "SALES")

    logger.info(f"✍️  [WRITER {mode}] Piszę dla {company.name} (Step {lead.step_number})...")

    # Dynamiczny model z konfiguracji klienta
    writer_model = getattr(client, "writer_model", None) or DEFAULT_MODEL
    logger.info(f"   🧠 Model: {writer_model}")

    # --- 1. PARSOWANIE DANYCH Z RESEARCHU ---
    research_data = _parse_research_summary(lead.ai_analysis_summary or "")
    logger.info(f"   🔍 Verified contact: {research_data['verified_contact_name']}")
    logger.info(f"   🎣 Icebreaker: {research_data['icebreaker'][:60] if research_data['icebreaker'] else 'Brak'}")

    # --- 2. POWITANIE — WYŁĄCZNIE ZWERYFIKOWANE IMIĘ ---
    greeting_name = _resolve_greeting(research_data["verified_contact_name"])
    logger.info(f"   📧 Greeting: {greeting_name or 'Dzień dobry,'}")

    # --- 3. SENDER / FOOTER / PŁEĆ ---
    sender_name = client.sender_name or None
    sender_gender = _detect_gender(sender_name)
    tone_key = _resolve_tone_key(getattr(client, "tone_of_voice", None))
    logger.info(f"   👤 Sender: {sender_name or '(brak)'} | Płeć: {'K' if sender_gender == 'F' else 'M'} | Ton: {tone_key} | Footer: {'TAK' if client.html_footer else 'NIE'}")

    # --- 3b. HISTORIA POPRZEDNICH MAILI (dla follow-upów) ---
    previous_emails = []
    if lead.step_number > 1:
        # Pobierz wcześniejsze maile do tej samej firmy w tej samej kampanii
        prev_leads = session.query(Lead).filter(
            Lead.campaign_id == lead.campaign_id,
            Lead.global_company_id == lead.global_company_id,
            Lead.step_number < lead.step_number,
            Lead.generated_email_subject.isnot(None),
        ).order_by(Lead.step_number).all()

        for pl in prev_leads:
            previous_emails.append({
                "step": pl.step_number,
                "subject": pl.generated_email_subject,
                "body": pl.generated_email_body or "",
            })
        logger.info(f"   📜 Historia: {len(previous_emails)} poprzednich maili")

    # --- 4. GENERATE EMAIL ---
    try:
        draft = _call_writer(
            client=client,
            company=company,
            greeting_name=greeting_name,
            research_data=research_data,
            step=lead.step_number,
            mode=mode,
            previous_emails=previous_emails,
            writer_model=writer_model,
            sender_gender=sender_gender,
            tone_key=tone_key,
        )
    except Exception as e:
        logger.error(f"❌ Writer error ({writer_model}): {e}")
        
        # --- PATIENCE DLA OVERLOADED (529) ---
        err_str = str(e).lower()
        if "529" in err_str or "overloaded" in err_str:
            try:
                from app.cache_manager import cache_manager
                retry_key = f"writer_overload_retry:{lead.id}"
                attempts = cache_manager.redis.incr(retry_key)
                if attempts == 1:
                    cache_manager.redis.expire(retry_key, 3600) # żyje 1h
                
                if attempts < 3:
                    logger.warning(f"   ⏳ API {writer_model} przeciążone (próba {attempts}/3). Zostawiam do ponowienia w następnym cyklu.")
                    return # Wychodzimy bez fallow-upu, status: ANALYZED
                else:
                    logger.warning(f"   🛑 {writer_model} zajęty przez 3 cykle. Czas na przymusowy FALLBACK.")
                    cache_manager.redis.delete(retry_key)
            except ImportError:
                pass # Brak cache (np. w testach) - fallujemy natychmiast
                
        # --- FALLBACK: próba z domyślnym modelem Gemini ---
        if writer_model != DEFAULT_MODEL:
            logger.warning(f"   🔄 FALLBACK: Próbuję z domyślnym modelem {DEFAULT_MODEL}...")
            try:
                draft = _call_writer(
                    client=client,
                    company=company,
                    greeting_name=greeting_name,
                    research_data=research_data,
                    step=lead.step_number,
                    mode=mode,
                    previous_emails=previous_emails,
                    writer_model=DEFAULT_MODEL,
                    sender_gender=sender_gender,
                    tone_key=tone_key,
                )
                logger.info(f"   ✅ FALLBACK OK — wygenerowano na {DEFAULT_MODEL}")
            except Exception as fallback_err:
                logger.error(f"❌ Fallback writer error: {fallback_err}")
                return
        else:
            return
    
    # --- 6. VALIDATE HTML ---
    safe_body = _sanitize_and_validate_html(draft.body)

    # --- 7. HALLUCINATION CHECK ---
    validation = _validate_against_data(
        safe_body,
        {'tech_stack': company.tech_stack, 'pain_points': company.pain_points},
        {'case_studies': client.case_studies}
    )
    
    if validation["is_hallucinating"]:
        logger.warning(f"⚠️  HALLUCINATION DETECTED: {validation['violations']}")
        logger.info(f"   🔄 Regenerating with strict mode...")
        
        draft = _call_writer(
            client=client,
            company=company,
            greeting_name=greeting_name,
            research_data=research_data,
            step=lead.step_number,
            mode=mode,
            previous_emails=previous_emails,
            strict_mode=True,
            writer_model=writer_model,
            sender_gender=sender_gender,
            tone_key=tone_key,
        )
        safe_body = _sanitize_and_validate_html(draft.body)
        validation = _validate_against_data(safe_body, {}, {})

    score = validation["confidence_score"]

    # --- 8. ASSEMBLE FINAL EMAIL: body → podpis → stopka → RODO ---
    # Writer generuje TYLKO treść (bez podpisu). Reszta doklejana programowo.
    complete_body = safe_body

    # 8a. Podpis osobisty — zawsze jeśli mamy sender_name
    if sender_name:
        complete_body += f"<br><br><p>Pozdrawiam,<br/>{sender_name}</p>"

    # 8b. Stopka HTML klienta (branding / logo / dane firmy) — z bazy
    if client.html_footer:
        complete_body += f"<br>{client.html_footer}"

    # 8c. Obowiązkowa klauzula RODO (opt-out przez odpowiedź "Wypisz")
    # ADO = nazwa prawna z KRS (legal_name), NIE nazwa projektu/marki (client.name)
    rodo_admin_name = getattr(client, "legal_name", None) or client.name
    rodo_clause = generate_rodo_clause(
        client_name=rodo_admin_name,
        privacy_policy_url=getattr(client, "privacy_policy_url", None) or "#",
    )
    if rodo_clause:
        complete_body += rodo_clause

    # --- 9. SAVE TO DATABASE ---
    lead.generated_email_subject = draft.subject
    lead.generated_email_body = complete_body
    lead.ai_confidence_score = int(score)

    if lead.status != "MANUAL_CHECK":
        lead.status = "DRAFTED"

    lead.last_action_at = datetime.now(PL_TZ)
    session.commit()
    logger.info(f"   💾 Draft saved (Confidence: {score:.0f}%): '{draft.subject}'")

    # STATS: draft wygenerowany
    try:
        stats_manager.increment_drafted(session, client.id, count=1, confidence_score=float(score))
    except Exception:
        pass  # Stats nie mogą blokować pipeline'u


def _call_writer(
    client,
    company,
    greeting_name,
    research_data: dict,
    step=1,
    feedback=None,
    mode="SALES",
    previous_emails=None,
    strict_mode=False,
    writer_model: str = DEFAULT_MODEL,
    sender_gender: str = "M",
    tone_key: str = "professional",
):
    """
    ENGINE v5: Silnik generujący treść maila z systemem różnorodności.
    Dynamiczna persona, architektura otwarcia i few-shot per ton głosu klienta.
    """
    uvp = client.value_proposition or ""
    cases = client.case_studies or ""
    tone_of_voice = (getattr(client, "tone_of_voice", None) or "").strip()
    # negative_constraints zawiera MIESZANE zakazy (dla scoutingu I dla pisania).
    # Writer stosuje TYLKO te dotyczące treści, stylu i tematyki maila.
    # Zakazy dotyczące typów firm (np. "nie szukaj szpitali") są tu nieistotne.
    writing_constraints = client.negative_constraints or ""

    icebreaker = research_data.get("icebreaker") or ""
    company_summary = research_data.get("summary") or ""
    key_products = research_data.get("key_products") or ""
    pain_points = research_data.get("pain_points") or ""

    company_name = company.name or ""
    client_name = client.name or ""

    # --- POWITANIE (zawsze formalne — branże profesjonalne wymagają dystansu) ---
    greeting_line = "Dzień dobry,"

    # --- PODPIS (zawsze doklejany programowo — writer go NIE generuje) ---
    signature_instruction = "ZAKOŃCZ mail na pytaniu lub CTA. NIE dodawaj podpisu, stopki ani 'Pozdrawiam' — to jest doklejane automatycznie przez system."

    # --- HISTORIA POPRZEDNICH MAILI (kontekst dla follow-upów) ---
    history_block = ""
    if previous_emails:
        history_lines = []
        for prev in previous_emails:
            # Wyciągamy czysty tekst z HTML (usuwamy tagi) — krótszy kontekst
            body_clean = re.sub(r'<[^>]+>', ' ', prev["body"])
            body_clean = re.sub(r'\s+', ' ', body_clean).strip()
            # Obcinamy do ~200 znaków żeby nie zaśmiecić kontekstu
            if len(body_clean) > 200:
                body_clean = body_clean[:200] + "..."
            history_lines.append(f"Mail {prev['step']}:\n  Temat: {prev['subject']}\n  Treść: {body_clean}")
        history_block = "\n\n".join(history_lines)

    # --- ICEBREAKER ---
    if icebreaker and icebreaker not in ("Brak", "NULL", ""):
        icebreaker_instruction = f'Użyj tego faktu jako punkt wyjścia pierwszego zdania po powitaniu (parafrazuj naturalnie, nie kopiuj):\n"{icebreaker}"'
    else:
        icebreaker_instruction = (
            "Brak konkretnego faktu z researchu. Pierwszym zdaniem po powitaniu "
            "zasygnalizuj że znasz ich branżę — krótka, trafna obserwacja. "
            "NIE pisz komplementu ani ogólnika."
        )

    # --- DANE O FIRMACH (kontekst) ---
    tone_block = f"\nTON GŁOSU I STYL: {tone_of_voice}" if tone_of_voice else ""

    writing_constraints_block = ""
    if writing_constraints.strip():
        writing_constraints_block = (
            f"\nOGRANICZENIA TREŚCI I STYLU (stosuj je do pisania — ignoruj zakazy dotyczące typów firm):\n"
            f"{writing_constraints}"
        )

    data_block = f"""ODBIORCA (firma do której piszemy):
- Nazwa: {company_name}
- Profil: {company_summary or "brak danych"}
- Usługi/Produkty: {key_products or "brak danych"}
- Możliwe potrzeby: {pain_points or "brak danych"}

NADAWCA (w czyim imieniu piszemy):
- Firma: {client_name}
- Branża nadawcy: {client.industry or "brak danych"}
- Co oferujemy: {uvp or "brak danych"}
- Kogo szukamy (ICP): {(client.ideal_customer_profile or "")[:200] or "brak danych"}
- Case studies: {cases or "brak"}{tone_block}{writing_constraints_block}"""

    # --- TASK: CO PISAĆ ---
    # Dynamiczna forma gramatyczna (rodzaj żeński/męski)
    if sender_gender == "F":
        _widzialem = "Widziałam"
        _zauwazyl = "Zauważyłam"
        _zastawialem = "Zastanawiałam się"
        _wracam = "Wracam"
        _pomyslalem = "Pomyślałam o jeszcze jednej rzeczy"
    else:
        _widzialem = "Widziałem"
        _zauwazyl = "Zauważyłem"
        _zastawialem = "Zastanawiałem się"
        _wracam = "Wracam"
        _pomyslalem = "Pomyślałem o jeszcze jednej rzeczy"

    if mode == "JOB_HUNT":
        if step == 1:
            task_block = f"""ZADANIE: Mail aplikacyjny (szukam pracy).

Schemat:
1. Powitanie
2. Jedno zdanie — co konkretnego {_zauwazyl.lower()} u nich (z danych)
3. Kim jestem i co robię — 1-2 zdania, konkrety
4. Jeden dowód (projekt, wynik, technologia)
5. CTA: jedno pytanie ("Szukacie kogoś w tym kierunku?")"""
        else:
            task_block = f"""ZADANIE: Follow-up nr {step} do wcześniejszego maila aplikacyjnego.

Schemat:
1. Powitanie
2. Nawiąż krótko ("{_wracam} do tematu" / "{_pomyslalem}")
3. Dodaj NOWĄ wartość — inna umiejętność, obserwacja, pytanie
4. Miękkie CTA"""
    else:  # SALES
        # ENGINE v5: Dynamiczny wybór architektury otwarcia
        strategy = _select_opening_strategy(step, previous_emails)
        strategy_instruction = strategy["instruction"]
        # Format gender forms in follow-up strategy templates
        strategy_instruction = strategy_instruction.replace("{_wracam}", _wracam)
        strategy_instruction = strategy_instruction.replace("{_zastawialem}", _zastawialem)
        logger.info(f"   🎯 Strategia: {strategy['name']} ({strategy['id']})")

        if step == 1:
            task_block = f"""ZADANIE: Pierwszy cold email (zapytanie analityczne).

Schemat:
1. Powitanie
2. Hook — jedno zdanie oparte na icebreaker/researchu. Pokaż że analizujesz ich branżę.
{strategy_instruction}
4. Zapytanie (CTA) — czyste pytanie o otwartość na rozmowę.
WAŻNE: Zakaz używania stwierdzeń "robimy to", "pomagamy w", "nasza oferta to".
NIGDY nie stosuj sformułowania "Współpracując z podobnymi..." — to zakazana fraza.
(Bez podpisu — doklejany automatycznie)"""
        else:
            task_block = f"""ZADANIE: Follow-up nr {step} (podtrzymanie zapytania analitycznego).

Schemat:
1. Powitanie
{strategy_instruction}
4. Lekkie CTA (pytanie o otwartość na rozmowę)
WAŻNE: Zakaz używania stwierdzeń "robimy to", "pomagamy w", "nasza oferta to".
WAŻNE: NIGDY nie powtórz argumentu/frazy z poprzedniego maila.
(Bez podpisu — doklejany automatycznie)"""

    # --- SYSTEM PROMPT: PERSONA + REGUŁY + PRZYKŁADY ---
    # ENGINE v5: Persona dynamiczna per ton głosu
    persona = _build_persona(tone_key, sender_gender)

    tone_of_voice_rule = ""
    if tone_of_voice:
        tone_of_voice_rule = f"\n=== TON GŁOSU (PRIORYTET NADRZĘDNY) ===\nKlient zdefiniował wymagany styl komunikacji: {tone_of_voice}\nKażde zdanie maila MUSI odzwierciedlać ten ton. To wymóg niepodlegający negocjacji.\n"

    system_prompt = f"""{persona}
{tone_of_voice_rule}
Twoje zasady życiowe jako handlowca:
- Piszesz krótko. Nikt nie czyta esejów od nieznajomych.
- Każde zdanie musi nieść informację. Jeśli zdanie można usunąć bez straty sensu — usuń je.
- Nie komplementujesz ("Wasza firma jest świetna!"). To brzmi fałszywie.
- Nie prosisz o czas ("Czy moglibyśmy porozmawiać?"). Zamiast tego pytasz o problem.
- Nie sprzedajesz w pierwszym mailu. Budujesz ciekawość.
- Piszesz tak, jakbyś pisał do znajomego z branży — z szacunkiem, ale bez sztywności.

=== 🛑 ZASADA TWARDEGO TRZYMANIA SIĘ FAKTÓW 🛑 ===
ABSOLUTNY ZAKAZ zgadywania i dodawania usług, programów, procedur ani cech odbiorcy, których nie ma wprost wymienionych w sekcji DANE (w szczególności w 'Icebreaker' lub 'Profil').
Jeśli wiesz jaka to branża (np. "Ośrodek Zdrowia"), NIE WOLNO Ci zmyślać i wymieniać standardowych usług dla tej branży (np. "szczepienia, opieka pielęgniarska"), chyba że badanie wprost to potwierdziło!
Wymyślanie usług to kłamstwo, które rujnuje rzetelność w zimnych mailach. Lepiej sformułować to ogólnie (np. "rozliczenia NFZ w Państwa przychodni"), niż zmyślać konkretne procedury! Działaj TYLKO na twardych danych.

=== DANE ===
{data_block}

=== ICEBREAKER ===
{icebreaker_instruction}

=== POWITANIE ===
Pierwsza linia maila (body) to DOKŁADNIE: "{greeting_line}"
Po niej — pierwsze zdanie merytoryczne (hook/icebreaker).

=== PODPIS ===
{signature_instruction}

=== HISTORIA KORESPONDENCJI ===
{history_block if history_block else "Brak — to pierwszy mail do tej firmy."}
WAŻNE: Jeśli są poprzednie maile — NIE powtarzaj tych samych argumentów, CTA ani fraz. Każdy follow-up musi wnosić NOWĄ wartość.

=== {task_block} ===

=== FORMAT ===
- HTML: używaj TYLKO <p> i <br>. Żadnych <b>, <strong>, <ul>, <li>, <h1> itp.
- Każdy akapit w osobnym <p>. Max 2-3 zdania na akapit.
- Całość: 60-100 słów (bez podpisu). To mail, nie artykuł.
- Temat (subject): 3-5 słów, brzmi jak wewnętrzna wiadomość, nie reklama.

=== ZAKAZANE ZWROTY (użycie = dyskwalifikacja) ===
Kategoria 1 — AI-izmy (natychmiast zdradzają bota):
"Z przyjemnością", "Rozumiem że", "Oczywiście", "Absolutnie", "Doskonale",
"Chciałbym zaproponować", "Pozwolę sobie", "Mam nadzieję że ten mail",
"W nawiązaniu do", "Zwracam się z", "Pragnę przedstawić"

Kategoria 2 — korporacyjne frazesy (nikt tak nie mówi):
"kompleksowe rozwiązania", "innowacyjne podejście", "wychodzimy naprzeciw",
"mamy przyjemność", "transformacja cyfrowa", "holistyczne podejście",
"synergia", "wartość dodana", "wymiana myśli", "wzajemne korzyści",
"dynamiczny rozwój", "w dzisiejszych czasach", "lider w branży",
"strategiczne partnerstwo", "umówić się na rozmowę"

Kategoria 3 — puste obietnice i zwroty sprzedażowe (bez pokrycia lub naruszające UŚUDE):
"zwiększymy Waszą sprzedaż", "oferujemy Państwu", "świadczymy usługi",
"nasze zindywidualizowane usługi pomogą", "kierujemy do państwa ofertę",
"Współpracując z podobnymi", "eliminujemy chaos", "kompleksowo",
"rozliczenia, prawo, administracja i wzrost przychodów w jednym miejscu"
wszelkie liczby/procenty/statystyki których NIE MA w danych powyżej

=== ZAKAZANE KONSTRUKCJE ===
- Nawiasy kwadratowe w treści: [cokolwiek]
- Nawiasy klamrowe w treści
- Pytania retoryczne ("Czy zastanawialiście się...?")
- Zdania zaczynające się od "Widzę że", "Zauważyłem że" (jeśli nie masz konkretu)
- "Chciałbym się umówić na" / "Może znajdziemy czas na"
- Więcej niż jedno pytanie w CTA

{_select_few_shots(tone_key, sender_gender)}

=== TWÓJ WEWNĘTRZNY PROCES (nie pisz tego w mailu) ===
1. Przeczytaj dane o odbiorcy. Co WIEM na pewno?
2. Jaki mają problem który mogę rozwiązać? (Jeśli nie wiem — pytam ogólnie o branżę)
3. Jak połączyć ich problem z naszą ofertą w JEDNYM zdaniu?
4. Jakie jedno pytanie zadam na końcu?
5. Sprawdź: czy każde zdanie mówi coś nowego? Czy cokolwiek brzmi "botowo"? Usuń."""

    if strict_mode:
        system_prompt += """

TRYB ŚCISŁY — dodatkowe ograniczenia:
- Każde zdanie MUSI mieć podstawę w danych powyżej. Zero spekulacji.
- Jeśli danych jest mało — mail ma być KRÓTSZY (40-60 słów), nie dłuższy z wymyślonymi faktami.
- Lepszy jest krótki prawdziwy mail niż długi z halucynacjami."""

    user_message = "Napisz subject i body (HTML). Trzymaj się schematu i danych. Zero wymysłów."
    if feedback:
        user_message += f"\n\nPoprawki od klienta: {feedback}"

    # ENGINE v5: Dynamiczne parametry LLM per ton głosu
    _tp = _TONE_PROFILES.get(tone_key, _TONE_PROFILES["professional"])
    writer_llm = create_structured_llm(writer_model, EmailDraft, temperature=_tp["temperature"], top_p=_tp["top_p"], top_k=_tp["top_k"])

    return writer_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ])


def _call_auditor(draft, company, client):
    """
    Opcjonalny krok weryfikacji.
    Auditor zawsze działa z temperature=0.0 — zimny, bezwzględny analityk.
    """
    auditor_model = getattr(client, "writer_model", None) or DEFAULT_MODEL
    auditor_llm = create_structured_llm(auditor_model, AuditResult, temperature=0.0)

    system_prompt = f"""Jesteś krytycznym korektorem emaili.

CRITERIA:
1. Human-like: Czy brzmi jak człowiek?
2. Specific: Concrete details from research
3. No hallucinations: All verified data
4. Mobile-readable: Short paragraphs
5. Clear CTA: Do they know what to do?

SCORING: 0-100 (90+ = send, 70-89 = improve, <70 = reject)"""

    user_prompt = f"""Subject: {draft.subject}
Body: {draft.body}

Oceń i daj konkretny feedback."""

    return auditor_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
