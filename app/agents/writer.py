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
            "Jesteś doświadczonym handlowcem z 15-letnim stażem w sprzedaży B2B w Polsce. "
            "Piszesz po polsku — naturalnie, potocznie ale z klasą. Jak kolega z branży, nie jak korporacja.\n"
            "Twoje maile brzmią jakbyś pisał je ręcznie, szybko, konkretnie — bez szlifowania każdego słowa.\n\n"
            "JĘZYK: Piszesz WYŁĄCZNIE naturalną polszczyzną. NIGDY nie tłumacz angielskich idiomów dosłownie. "
            "Zamiast 'zostawiać pieniądze na stole' napisz 'tracić na kontrakcie'. "
            "Zamiast 'to zwykle sygnalizuje' napisz 'to często oznacza'. "
            "Zamiast 'generować realne straty' napisz 'kosztować'.\n\n"
            'RODZAJ MĘSKI. Zawsze: "widziałem", "zauważyłem", "zastanawiałem się".'
        ),
        "persona_f": (
            "Jesteś doświadczoną handlowczynią z 15-letnim stażem w sprzedaży B2B w Polsce. "
            "Piszesz po polsku — naturalnie, potocznie ale z klasą. Jak koleżanka z branży, nie jak korporacja.\n"
            "Twoje maile brzmią jakbyś pisała je ręcznie, szybko, konkretnie — bez szlifowania każdego słowa.\n\n"
            "JĘZYK: Piszesz WYŁĄCZNIE naturalną polszczyzną. NIGDY nie tłumacz angielskich idiomów dosłownie. "
            "Zamiast 'zostawiać pieniądze na stole' napisz 'tracić na kontrakcie'. "
            "Zamiast 'to zwykle sygnalizuje' napisz 'to często oznacza'. "
            "Zamiast 'generować realne straty' napisz 'kosztować'.\n\n"
            'RODZAJ ŻEŃSKI. Zawsze: "widziałam", "zauważyłam", "zastanawiałam się". NIGDY rodzaju męskiego.'
        ),
    },
    "formal": {
        "temperature": 0.60, "top_p": 0.80, "top_k": 35,
        "persona_m": (
            "Jesteś doradcą z wieloletnią praktyką. Piszesz oficjalnie ale PROSTO — jak człowiek, "
            "nie jak wzór z podręcznika. Zwracasz się per 'Państwo'.\n\n"
            "JĘZYK: Naturalny polski. Żadnych angielskich kalek językowych. "
            "Formalne ≠ sztuczne. Pisz jak dyrektor do dyrektora, nie jak robot.\n\n"
            'RODZAJ MĘSKI. "Zwróciłem uwagę", "przejrzałem". NIE używaj "pozwolę sobie".'
        ),
        "persona_f": (
            "Jesteś doradczynią z wieloletnią praktyką. Piszesz oficjalnie ale PROSTO — jak człowiek, "
            "nie jak wzór z podręcznika. Zwracasz się per 'Państwo'.\n\n"
            "JĘZYK: Naturalny polski. Żadnych angielskich kalek językowych. "
            "Formalne ≠ sztuczne. Pisz jak dyrektorka do dyrektora, nie jak robot.\n\n"
            'RODZAJ ŻEŃSKI. "Zwróciłam uwagę", "przejrzałam". NIE używaj "pozwolę sobie".'
        ),
    },
    "direct": {
        "temperature": 0.65, "top_p": 0.80, "top_k": 35,
        "persona_m": (
            "Jesteś praktykiem. Piszesz ultrakrótko — bez ozdobników, prosto do sedna. "
            "Każde zbędne słowo to słabość. Mówisz wprost.\n\n"
            'RODZAJ MĘSKI. "Widziałem", "sprawdziłem", "szukam".'
        ),
        "persona_f": (
            "Jesteś praktyczką. Piszesz ultrakrótko — bez ozdobników, prosto do sedna. "
            "Każde zbędne słowo to słabość. Mówisz wprost.\n\n"
            'RODZAJ ŻEŃSKI. "Widziałam", "sprawdziłam", "szukam".'
        ),
    },
    "technical": {
        "temperature": 0.55, "top_p": 0.75, "top_k": 30,
        "persona_m": (
            "Jesteś analitykiem z wiedzą branżową. Piszesz rzeczowo, konkretnymi terminami. "
            "Fakty — nie opinie. Dane — nie domysły.\n\n"
            'RODZAJ MĘSKI. "Przeanalizowałem", "sprawdziłem", "zmapowałem".'
        ),
        "persona_f": (
            "Jesteś analityczką z wiedzą branżową. Piszesz rzeczowo, konkretnymi terminami. "
            "Fakty — nie opinie. Dane — nie domysły.\n\n"
            'RODZAJ ŻEŃSKI. "Przeanalizowałam", "sprawdziłam", "zmapowałam".'
        ),
    },
}

# 6 architektur otwarcia cold maila (SALES step==1)
_OPENING_STRATEGIES_COLD: list[dict] = [
    {
        "id": "diagnostic_question",
        "name": "Pytanie Diagnostyczne",
        "instruction": (
            '3. Zadaj JEDNO konkretne pytanie o ich proces/wyzwanie — potem daj 1 zdanie '
            'dlaczego pytasz (z własnego doświadczenia, NIE z ich strony).\n'
            '   Przykład struktury: "Jak u Państwa wygląda [proces z danych]? '
            'Pytam, bo w podobnych placówkach to bywa problematyczne."\n'
            '   WAŻNE: Pytanie MUSI dotyczyć czegoś widocznego w danych. Nie zmyślaj.'
        ),
    },
    {
        "id": "one_fact_one_question",
        "name": "Fakt + Pytanie",
        "instruction": (
            '3. Weź JEDEN konkretny fakt z danych o odbiorcy (np. zakres usług, programy, '
            'liczbę poradni) i zadaj pytanie, które naturalnie z tego wynika.\n'
            '   Przykład: "Prowadzicie [fakt z danych]. Przy takiej skali — kto u Was pilnuje '
            'rozliczeń na bieżąco?"\n'
            '   WAŻNE: Fakt MUSI być z researchu. Pytanie MUSI być naturalne, krótkie, '
            'ludzkie. NIE pisz "to zwykle sygnalizuje" ani "w podobnych strukturach".'
        ),
    },
    {
        "id": "inverted_perspective",
        "name": "Odwrócona Perspektywa",
        "instruction": (
            '3. Pokaż dwa sposoby, jak firmy z ich branży radzą sobie z jednym problemem. '
            'Zapytaj jak oni to robią.\n'
            '   Przykład: "Jedni robią [A], inni [B]. Ciekawi mnie, jak to wygląda u Was."\n'
            '   WAŻNE: Oba podejścia muszą być realne i krótko opisane.'
        ),
    },
    {
        "id": "pain_point_bridge",
        "name": "Problem z Danych",
        "instruction": (
            '3. Weź pain point z sekcji "Możliwe potrzeby" i opisz go JEDNYM zdaniem. '
            'Nie obiecuj rozwiązania — tylko pokaż że rozumiesz problem.\n'
            '   Przykład: "[Problem z danych] — to temat, który przy [ich skali] '
            'zaczyna być uciążliwy."\n'
            '   WAŻNE: Problem MUSI być z danych. NIE wymyślaj problemów.'
        ),
    },
    {
        "id": "market_trend",
        "name": "Trend Rynkowy",
        "instruction": (
            '3. Opisz JEDNYM zdaniem co się zmienia w ich branży i zapytaj '
            'czy to ich dotyczy.\n'
            '   Przykład: "Coraz więcej [typ firm] zaczyna [trend]. '
            'Dajcie znać, czy to u Was też temat."\n'
            '   WAŻNE: Trend musi być prawdziwy i powiązany z ofertą nadawcy.'
        ),
    },
    {
        "id": "honest_observation",
        "name": "Szczera Obserwacja",
        "instruction": (
            '3. Opisz co WIDZISZ na ich stronie/w danych — bez wyciągania wniosków. '
            'Potem zadaj proste pytanie.\n'
            '   Przykład: "Na stronie widziałam [konkret]. Zastanawiam się, '
            'czy [proste pytanie o ich proces]."\n'
            '   WAŻNE: NIE łącz przypadkowych faktów (np. IOD → rozliczenia). '
            'Jeśli nie ma logicznego powiązania, zadaj ogólniejsze pytanie o ich branżę.'
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


# --- PULA PRZYKŁADÓW FEW-SHOT (5 per ton, indeksowane kluczem tonu) ---
# ZASADA: Przykłady definiują styl MOCNIEJ niż reguły. Każdy few-shot to wzór idealnego maila.
# Język: naturalny polski, zero angielskich kalek, krótko, konkretnie, jak człowiek.
_FEW_SHOT_POOL: dict[str, list[dict]] = {
    "professional": [
        {
            "label": "cold, z icebreakerem, pytanie o proces",
            "subject": "rozliczenia NFZ",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Na Państwa stronie {_widzialem}, że prowadzicie opiekę koordynowaną "
                "w trzech ścieżkach — kardiologia, diabetologia i endokrynologia. "
                "To trzy oddzielne strumienie rozliczeń z NFZ prowadzone równolegle.</p>"
                "<p>Macie kogoś, kto pilnuje tego na bieżąco, czy to wciąż "
                "jedna osoba do wszystkiego?</p>"
            ),
        },
        {
            "label": "cold, bez icebrakera, obserwacja branżowa",
            "subject": "kwestia kontraktu",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Placówki POZ z kilkoma programami NFZ jednocześnie — CHUK, "
                "opieka koordynowana, profilaktyka — rzadko mają czas pilnować, "
                "czy nic im nie ucieka przy rozliczeniach.</p>"
                "<p>Sprawdzacie to u siebie regularnie, czy raczej reaktywnie?</p>"
            ),
        },
        {
            "label": "cold, trend rynkowy",
            "subject": "zmiany w rozliczeniach",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Od stycznia NFZ zmienił zasady finansowania opieki koordynowanej "
                "— nowe dodatki motywacyjne, ale też kary za brak aktywności przez "
                "3 miesiące.</p>"
                "<p>Śledzicie te zmiany na bieżąco, czy to temat, "
                "którym warto się zająć?</p>"
            ),
        },
        {
            "label": "follow-up, nowy kąt",
            "subject": "Re: rozliczenia NFZ",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_wracam} z jedną myślą. Rozmawiając z innymi przychodniami, "
                "słyszę że największy problem to nie same rozliczenia — tylko to, "
                "że nikt nie ma czasu ich weryfikować, dopóki NFZ nie zakwestionuje.</p>"
                "<p>Jak to u Was wygląda?</p>"
            ),
        },
        {
            "label": "follow-up, pytanie pogłębiające",
            "subject": "Re: rozliczenia NFZ",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_zastawialem} nad jedną rzeczą — przy tylu programach "
                "równolegle, kto u Państwa odpowiada za pilnowanie terminów "
                "sprawozdawczości do NFZ?</p>"
                "<p>Chętnie opowiem, jak inne placówki to rozwiązują, "
                "jeśli to w ogóle temat.</p>"
            ),
        },
    ],
    "formal": [
        {
            "label": "cold, z icebreakerem, formalny",
            "subject": "kwestia rozliczeń",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Przejrzałem zakres Państwa działalności — POZ, specjalistyka "
                "i diagnostyka w jednej strukturze. To spory zakres dokumentacji "
                "i rozliczeń z NFZ po jednej stronie.</p>"
                "<p>Czy weryfikacja szczelności kontraktu to temat, "
                "który Państwo obecnie poruszacie?</p>"
            ),
        },
        {
            "label": "cold, bez icebrakera, formalny",
            "subject": "pytanie o procesy",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Placówki o zbliżonym profilu do Państwa coraz częściej "
                "zgłaszają się do nas z pytaniem o optymalizację rozliczeń "
                "z płatnikiem publicznym.</p>"
                "<p>Czy to obszar, w którym widzicie Państwo "
                "potrzebę zmian?</p>"
            ),
        },
        {
            "label": "follow-up, formalny",
            "subject": "Re: pytanie o procesy",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Wracam do tematu z dodatkową obserwacją. W ostatnich miesiącach "
                "NFZ zaostrzył wymagania wobec placówek realizujących opiekę "
                "koordynowaną — straciło na tym kilka przychodni w regionie.</p>"
                "<p>Gdyby chcieli Państwo to skonsultować — jestem do dyspozycji.</p>"
            ),
        },
        {
            "label": "cold, pytanie diagnostyczne, formalny",
            "subject": "dokumentacja kontraktowa",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Zauważyłem, że Państwa placówka realizuje jednocześnie "
                "kilka programów profilaktycznych NFZ. Przy tej skali — "
                "jak wygląda u Państwa kontrola poprawności sprawozdań?</p>"
                "<p>Pytam, bo to najczęstszy punkt, w którym placówki "
                "tracą na kontrakcie.</p>"
            ),
        },
        {
            "label": "follow-up, zmiana perspektywy, formalny",
            "subject": "Re: dokumentacja kontraktowa",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Patrząc na ten temat z innej strony — nawet jeśli rozliczenia "
                "Państwo mają pod kontrolą, to pytanie brzmi: czy ktoś weryfikuje, "
                "czy nie przysługują Wam dodatkowe środki z nowych programów NFZ.</p>"
                "<p>Dajcie Państwo znać, jeśli warto to omówić.</p>"
            ),
        },
    ],
    "direct": [
        {
            "label": "cold, z icebreakerem, bezpośredni",
            "subject": "szybkie pytanie",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_widzialem} że prowadzicie trzy programy NFZ naraz. "
                "To sporo papierkowej roboty na jedną administrację.</p>"
                "<p>Ogarniecie to sami, czy szukacie wsparcia?</p>"
            ),
        },
        {
            "label": "cold, bez icebrakera, bezpośredni",
            "subject": "jedno pytanie",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Przychodnie z kontraktem NFZ w kilku zakresach naraz "
                "tracą średnio kilka procent kontraktu na błędach w raportowaniu. "
                "Mało kto to sprawdza na bieżąco.</p>"
                "<p>Weryfikujecie to u siebie?</p>"
            ),
        },
        {
            "label": "follow-up, bezpośredni",
            "subject": "Re: jedno pytanie",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_wracam} krótko — od stycznia NFZ zmienił zasady "
                "finansowania. Część placówek straciła na tym nie wiedząc. "
                "Warto sprawdzić, czy Was to dotyczy.</p>"
                "<p>Pogadamy?</p>"
            ),
        },
        {
            "label": "cold, problem z danych, bezpośredni",
            "subject": "kontrakt NFZ",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>POZ plus specjalistyka plus programy profilaktyczne — "
                "to trzy różne rozliczenia w jednej przychodni. "
                "Przy takiej skali łatwo coś przeoczyć.</p>"
                "<p>Macie to pod kontrolą?</p>"
            ),
        },
        {
            "label": "follow-up, nowy kąt, bezpośredni",
            "subject": "Re: kontrakt NFZ",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_wracam} z jedną obserwacją — placówki, które robią "
                "audyt rozliczeń, zwykle odkrywają że mogą wyciągnąć więcej "
                "z istniejącego kontraktu. Bez dodatkowej pracy.</p>"
                "<p>Interesuje Was taki temat?</p>"
            ),
        },
    ],
    "technical": [
        {
            "label": "cold, z icebreakerem, techniczny",
            "subject": "sprawozdawczość NFZ",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_widzialem} że Państwa placówka realizuje opiekę koordynowaną, "
                "CHUK i standardowe świadczenia POZ jednocześnie. "
                "To oznacza trzy odrębne procesy sprawozdawcze do NFZ.</p>"
                "<p>Jak wygląda u Was weryfikacja poprawności danych "
                "przed wysyłką do płatnika?</p>"
            ),
        },
        {
            "label": "cold, bez icebrakera, techniczny",
            "subject": "procesy rozliczeniowe",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Pracując z placówkami o podobnym zakresie kontraktu, "
                "widzimy powtarzający się wzorzec — błędy w kodowaniu procedur "
                "ICD-10 i rozliczaniu wizyt koordynowanych kosztują "
                "konkretne pieniądze na kontrakcie.</p>"
                "<p>Monitorujecie tę stronę u siebie?</p>"
            ),
        },
        {
            "label": "follow-up, techniczny",
            "subject": "Re: procesy rozliczeniowe",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_wracam} z konkretną obserwacją — od stycznia 2026 "
                "NFZ wymaga od placówek z opieką koordynowaną utrzymania "
                "minimum 5%% pacjentów w programie, inaczej tracą "
                "podwyższoną stawkę kapitacyjną.</p>"
                "<p>Sprawdzaliście, jak to wygląda u Was liczbowo?</p>"
            ),
        },
        {
            "label": "cold, fakt + pytanie, techniczny",
            "subject": "struktura kontraktu",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>Na Państwa stronie widziałem zakres obejmujący "
                "poradnie specjalistyczne i POZ w jednej strukturze. "
                "Przy takim modelu — rozliczenia idą jednym raportem "
                "czy każdy zakres osobno?</p>"
                "<p>Pytam, bo to wpływa na to, ile można wyciągnąć "
                "z kontraktu.</p>"
            ),
        },
        {
            "label": "follow-up, pytanie pogłębiające, techniczny",
            "subject": "Re: struktura kontraktu",
            "body": (
                "<p>Dzień dobry,</p>"
                "<p>{_zastawialem} nad jedną kwestią — przy równoległym "
                "prowadzeniu POZ i opieki koordynowanej, czy Państwa system "
                "gabinetowy prawidłowo taguje wizyty pod odpowiedni kontrakt?</p>"
                "<p>To częsty punkt, w którym placówki tracą na rozliczeniach "
                "nie wiedząc o tym.</p>"
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
=== ZASADY (3 najważniejsze) ===
1. KRÓTKO. Nikt nie czyta esejów od nieznajomych. 60-100 słów max.
2. KONKRETNIE. Każde zdanie musi nieść nową informację. Jeśli zdanie można usunąć bez straty sensu — usuń.
3. NIE SPRZEDAWAJ. Nie mów co oferujesz. Pytaj o ICH problem. Buduj ciekawość, nie prezentację.

=== 🛑 ZERO HALUCYNACJI — TWARDY FAKT 🛑 ===
ABSOLUTNY ZAKAZ zgadywania i dodawania usług, programów, procedur ani cech odbiorcy, których NIE MA wymienionych w sekcji DANE.
Jeśli wiesz jaka to branża (np. "Ośrodek Zdrowia"), NIE WOLNO Ci zmyślać standardowych usług tej branży (np. "szczepienia, opieka pielęgniarska"), chyba że research to wprost potwierdził!
Lepiej napisać ogólnie ("rozliczenia NFZ w Państwa przychodni") niż zmyślić procedurę. Działaj TYLKO na twardych danych.

=== JĘZYK — NATURALNY POLSKI ===
Piszesz po polsku, jak normalny człowiek. NIE tłumacz angielskich zwrotów dosłownie.
Złe: "zostawiać pieniądze na stole" → Dobre: "tracić na kontrakcie"
Złe: "to zwykle sygnalizuje" → Dobre: "to często oznacza"
Złe: "generować realne straty" → Dobre: "kosztować"
Złe: "punkt styku z płatnikiem" → Dobre: "rozliczenia z NFZ"
Złe: "wymaga uwagi" → Dobre: "warto sprawdzić"
Złe: "jest aktywny po Państwa stronie" → Dobre: "zajmujecie się tym"

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

=== CTA — ZAKOŃCZENIE MAILA ===
Końcowe pytanie MUSI brzmieć naturalnie. Wylosuj JEDEN wariant z puli (nigdy nie powtarzaj w kolejnych mailach):
- "Macie to ogarnięte, czy szukacie wsparcia?"
- "Sprawdzacie to u siebie regularnie?"
- "Dajcie znać, jeśli warto o tym pogadać."
- "Zajmujecie się tym wewnętrznie?"
- "Jak to u Was wygląda?"
- "Interesuje Was ten temat?"
- "Weryfikujecie to u siebie?"
- "Pogadamy?"
NIE używaj: "Czy to temat, który jest teraz aktualny?" (za sztywne)
NIE używaj: "Czy bylibyście otwarci na..." (za korporacyjne)

=== ZAKAZANE ZWROTY (użycie = dyskwalifikacja) ===

Kategoria 1 — AI-izmy (natychmiast zdradzają bota):
"Z przyjemnością", "Rozumiem że", "Oczywiście", "Absolutnie", "Doskonale",
"Chciałbym zaproponować", "Pozwolę sobie", "Mam nadzieję że ten mail",
"W nawiązaniu do", "Zwracam się z", "Pragnę przedstawić",
"to zwykle sygnalizuje", "to zwykle oznacza że", "mogę sobie wyobrazić"

Kategoria 2 — korporacyjne frazesy:
"kompleksowe rozwiązania", "innowacyjne podejście", "wychodzimy naprzeciw",
"mamy przyjemność", "transformacja cyfrowa", "holistyczne podejście",
"synergia", "wartość dodana", "wymiana myśli", "wzajemne korzyści",
"dynamiczny rozwój", "w dzisiejszych czasach", "lider w branży",
"strategiczne partnerstwo", "umówić się na rozmowę", "podjąć współpracę"

Kategoria 3 — puste obietnice (naruszające UŚUDE):
"zwiększymy Waszą sprzedaż", "oferujemy Państwu", "świadczymy usługi",
"nasze usługi pomogą", "kierujemy do państwa ofertę",
"Współpracując z podobnymi", "eliminujemy chaos", "kompleksowo",
wszelkie liczby/procenty/statystyki których NIE MA w danych powyżej

Kategoria 4 — angielskie kalki (marker AI w polskim tekście):
"zostawiać pieniądze na stole", "nie zostawia pieniędzy na stole",
"zaczyna wymagać uwagi", "generować realne straty", "punkt styku z płatnikiem",
"w podobnych strukturach", "wielowarstwowe raportowanie",
"jest aktywny po Państwa stronie", "ma Państwa uwagę",
"jest dla Państwa aktualny", "jest przedmiotem Państwa uwagi",
"nie informuje publicznie" (truizm — nikt tego nie robi)

Kategoria 5 — naciągane implikacje (budują fałszywe wnioski):
NIE łącz przypadkowych faktów ze strony (np. "mają IOD" → "pewnie mają problemy z rozliczeniami").
NIE pisz "to zwykle sygnalizuje, że..." — to zawsze brzmi jak bot.
Jeśli nie masz LOGICZNEGO połączenia między faktem a wnioskiem — nie wymuszaj go.

=== ZAKAZANE KONSTRUKCJE ===
- Nawiasy kwadratowe w treści: [cokolwiek]
- Nawiasy klamrowe w treści
- Pytania retoryczne ("Czy zastanawialiście się...?")
- "Chciałbym się umówić na" / "Może znajdziemy czas na"
- Więcej niż jedno pytanie w CTA

{_select_few_shots(tone_key, sender_gender)}

=== WEWNĘTRZNY CHECKLIST (nie pisz tego w mailu) ===
1. Co WIEM na pewno o odbiorcy? (tylko z danych)
2. Czy każde zdanie mówi coś NOWEGO?
3. Czy cokolwiek brzmi jak bot albo przetłumaczony angielski? → Usuń/przepisz.
4. Czy CTA to JEDNO proste pytanie?
5. Przeczytaj mail na głos — czy tak mówi normalny Polak?"""

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

    system_prompt = f"""Jesteś bezwzględnym korektorem cold maili B2B. Oceniasz po polsku.

KRYTERIA (każde oceniasz 0-20, suma = score):

1. NATURALNY POLSKI (0-20):
   Czy mail brzmi jak napisany przez Polaka z doświadczeniem w sprzedaży?
   RED FLAGS: przetłumaczone angielskie idiomy ("zostawiać pieniądze na stole",
   "to zwykle sygnalizuje", "generować straty", "punkt styku", "wymaga uwagi"),
   korporacyjny żargon, zbyt formalne konstrukcje. 0 pkt = brzmi jak bot.

2. KONKRETNOŚĆ (0-20):
   Czy mail odnosi się do KONKRETNYCH danych o odbiorcy?
   Czy każde zdanie mówi coś nowego? 0 pkt = ogólniki bez treści.

3. ZERO HALUCYNACJI (0-20):
   Czy wszystkie informacje o odbiorcy są prawdziwe (z danych)?
   Czy nie wymyślono usług, programów, statystyk? 0 pkt = zmyślanie.

4. ZGODNOŚĆ Z RODO/UŚUDE (0-20):
   Czy mail NIE zawiera oferty handlowej, obietnic ani nachalnych CTA?
   Czy to "zapytanie analityczne" a nie sprzedaż? 0 pkt = wygląda jak spam.

5. CTA I ZAKOŃCZENIE (0-20):
   Czy kończy się JEDNYM prostym pytaniem?
   Czy pytanie brzmi naturalnie? 0 pkt = więcej niż jedno pytanie lub sztuczne CTA.

SCORING: 0-100 (90+ = wyślij, 70-89 = do poprawy, <70 = odrzuć)
Daj KONKRETNY feedback — co dokładnie jest złe i jak to naprawić."""

    user_prompt = f"""Subject: {draft.subject}
Body: {draft.body}

Oceń ten mail i daj konkretny feedback po polsku."""

    return auditor_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
