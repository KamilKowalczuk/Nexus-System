import os
import hmac
import hashlib
import base64
import logging
import re
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
    logger.info(f"   👤 Sender: {sender_name or '(brak)'} | Płeć: {'K' if sender_gender == 'F' else 'M'} | Footer: {'TAK' if client.html_footer else 'NIE'}")

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
        )
    except Exception as e:
        logger.error(f"❌ Writer error ({writer_model}): {e}")
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
):
    """
    ENGINE v4: Silnik generujący treść maila.
    Prompt-engineered pod Gemini 3.1 Pro — few-shot, persona, concrete anti-patterns.
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
- Co oferujemy: {uvp or "brak danych"}
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
        if step == 1:
            task_block = f"""ZADANIE: Pierwszy cold email (zapytanie analityczne).

Schemat:
1. Powitanie
2. Hook — jedno zdanie oparte na icebreaker/researchu. Pokaż że analizujesz ich branżę.
3. Obserwacja trendu (nie oferta) — 1-2 zdania. LOSOWO wybierz JEDEN z poniższych kątów wejścia (Matryca Rotacyjna). Każdy mail musi używać INNEJ ramy niż pozostałe:

   RAMA 1 (Hipoteza Badawcza): "Z mojego doświadczenia wynika hipoteza, że przy tej skali działalności [PROBLEM] zaczyna obciążać administrację. Czy to zjawisko występuje również u Państwa?"
   RAMA 2 (Analiza Trendu): "Obserwując ten segment rynku, mapujemy powtarzający się trend: [PROBLEM]. Czy to obszar, który obecnie weryfikujecie?"
   RAMA 3 (Korelacja Skali): "Zauważyliśmy pewną korelację — rozwój takich struktur często odsłania luki w [PROBLEM]. Czy bylibyście Państwo otwarci na krótką dyskusję, jak to wygląda u Was?"
   RAMA 4 (Audyt Zewnętrzny): "Analizując procesy podobnych podmiotów, identyfikujemy nieszczelności na etapie [PROBLEM]. Czy weryfikacja tego obszaru to coś, co mogłoby Was teraz zainteresować?"
   RAMA 5 (Sygnalizacja Rynkowa): "Według naszych obserwacji, firmy o zbliżonej strukturze coraz częściej raportują wyzwania w zakresie [PROBLEM]. Ciekawi mnie, czy to temat, na który zwracacie obecnie uwagę."
   RAMA 6 (Benchmark Branżowy): "Prowadząc analizę porównawczą w tym segmencie, trafiliśmy na powtarzalny wzorzec dotyczący [PROBLEM]. Bylibyście skłonni do krótkiej wymiany spostrzeżeń?"
   RAMA 7 (Pytanie Diagnostyczne): "Pracując z branżą, często słyszymy o wyzwaniach związanych z [PROBLEM]. Czy w Państwa przypadku to też punkt, który wymaga uwagi?"
   RAMA 8 (Obserwacja Strategiczna): "Przyglądając się obecnej dynamice tego rynku, [PROBLEM] wydaje się jednym z kluczowych punktów strategicznych. Czy poruszacie ten temat wewnętrznie?"

   Zastąp [PROBLEM] konkretnym wyzwaniem z danych o odbiorcy.
   NIGDY nie używaj dwóch tych samych ram w dwóch kolejnych wiadomościach.
   NIGDY nie stosuj sformułowania "Współpracując z podobnymi..." — to zakazana fraza.

4. Zapytanie (CTA) — czyste pytanie o otwartość na rozmowę.
WAŻNE: Zakaz używania stwierdzeń "robimy to", "pomagamy w", "nasza oferta to".
(Bez podpisu — doklejany automatycznie)"""
        else:
            task_block = f"""ZADANIE: Follow-up nr {step} (podtrzymanie zapytania analitycznego).

Schemat:
1. Powitanie
2. Nawiązanie ("{_wracam} z jedną myślą" / "{_zastawialem} nad czymś")
3. NOWY argument analityczny — użyj INNEJ ramy z Matrycy Rotacyjnej niż w poprzednim mailu. Możesz też użyć:
   - Nowej obserwacji z rynku lub statystyki
   - Pytania diagnostycznego o inny aspekt ich działalności
   - Odwołania do zmiany regulacyjnej lub trendu branżowego
4. Lekkie CTA ("Dajcie znać czy weryfikacja tego obszaru to w ogóle u Was temat")
WAŻNE: Zakaz używania stwierdzeń "robimy to", "pomagamy w", "nasza oferta to".
WAŻNE: NIGDY nie powtórz ramy/frazy z poprzedniego maila.
(Bez podpisu — doklejany automatycznie)"""

    # --- SYSTEM PROMPT: PERSONA + REGUŁY + PRZYKŁADY ---
    # Dynamiczna persona na podstawie płci sendera
    if sender_gender == "F":
        persona = f"""Jesteś doświadczoną handlowczyni B2B z 12-letnim stażem. Piszesz cold maile, które ludzie CZYTAJĄ i na które ODPOWIADAJĄ. Twoja siła: brzmisz jak normalna kobieta, nie jak bot ani korporacja.

WAŻNE: Piszesz w RODZAJU ŻEŃSKIM. Zawsze: "widziałam", "zauważyłam", "zastanawiałam się", "pracowałam", "rozmawiałam". NIGDY nie używaj rodzaju męskiego."""
    else:
        persona = f"""Jesteś doświadczonym handlowcem B2B z 12-letnim stażem. Piszesz cold maile, które ludzie CZYTAJĄ i na które ODPOWIADAJĄ. Twoja siła: brzmisz jak normalny człowiek, nie jak bot ani korporacja.

WAŻNE: Piszesz w RODZAJU MĘSKIM. Zawsze: "widziałem", "zauważyłem", "zastanawiałem się", "pracowałem", "rozmawiałem"."""

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

=== PRZYKŁADY DOBREGO STYLU ===

Przykład 1 (z icebreakerem):
Subject: automatyzacja procesów
Body:
<p>Dzień dobry,</p>
<p>{_widzialem} że rozbudowujecie zespół sprzedaży — trzy nowe oferty na LinkedIn w tym miesiącu. To zwykle moment, kiedy ręczne poszukiwanie procesów i budowa pipeline zaczynaja hamować skalowanie.</p>
<p>Współpracując z podmiotami o podobnej dynamice wzrostu, zauważyliśmy wyraźny wzorzec: automatyzacja dopływu leada eliminuje bottleneck cold callingu po stronie handlowców.</p>
<p>Czy bylibyście otwarci na krótką rozmowę, aby zweryfikować, czy nasze mechanizmy mogłyby usprawnić Wasz proces?</p>

Przykład 2 (bez icebrakera):
Subject: optymalizacja dla ERP
Body:
<p>Dzień dobry,</p>
<p>Analizując rynek firm IT wdrażających systemy B2B w Polsce, zwróciło moją uwagę Wasze osadzenie w segmencie ERP dla produkcji.</p>
<p>Nasz zespół analityczny zauważył, że dostarczanie zweryfikowanych zestawów kontaktów z konkretnych branż pozwala inżynierom zaoszczędzić około 15 godzin tygodniowo przeznaczanych w innej formie na manualny prospecting.</p>
<p>Czy rozważali Państwo weryfikację gotowych przepływów danych pod kątem optymalizacji waszych cykli poszukiwania kontraktów?</p>

Przykład 3 (follow-up):
Subject: Re: optymalizacja dla ERP
Body:
<p>Dzień dobry,</p>
<p>{_wracam} z jedną myślą — {_zastawialem.lower()} ostatnio nad rynkiem ERP i okazało się, z doświadczeń podobnych podmiotów, że największym problemem nie bywa brak danych analitycznych, ale brak tych wyselekcjonowanych.</p>
<p>Chętnie zaprezentuję na niezobowiązującym spotkaniu, w jakim stopniu nasze filtry mogłyby wesprzeć Państwa segmentację rynku.</p>

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

    writer_llm = create_structured_llm(writer_model, EmailDraft, temperature=0.72, top_p=0.85, top_k=40)

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
