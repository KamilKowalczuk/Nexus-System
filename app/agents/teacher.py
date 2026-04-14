# app/agents/teacher.py
"""
NEXUS TEACHER ENGINE — Dynamic AI Alignment (RLHF + Contrastive Prompting)

Nauczyciel asynchronicznie analizuje oceny operatora (1-5 ★ + komentarze),
syntetyzuje je i generuje skondensowaną "Księgę Zasad" (ClientAlignment).
Agenty wykonawcze (Writer, Researcher) wstrzykują tę księgę do swoich promptów.

Algorytm:
  1. Ingestion — pobierz stare reguły + nowy batch feedbacku
  2. Conflict Resolution — deduplikacja, nadpisywanie (nowsze wygrywa), kondensacja
  3. Contrastive Extraction — top 3 złotych + top 3 czarnych przykładów
  4. Archiwizacja — snapshot starej wersji do AlignmentHistory (max 10, FIFO)
  5. Persist — zapisz nowy ClientAlignment v(N+1)
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import (
    Client, Lead, GlobalCompany, Campaign,
    LeadFeedback, ClientAlignment, AlignmentHistory,
)
from app.schemas import TeacherSynthesisOutput
from app.model_factory import create_structured_llm, DEFAULT_MODEL

logger = logging.getLogger("nexus_teacher")

# ---------------------------------------------------------------------------
# KONFIGURACJA
# ---------------------------------------------------------------------------

_MAX_HISTORY_VERSIONS = 10      # Ile snapshotów trzymamy per klient (FIFO)
_MAX_POSITIVE_EXAMPLES = 3      # Ile złotych przykładów w alignment
_MAX_NEGATIVE_EXAMPLES = 3      # Ile czarnych przykładów w alignment
_TEACHER_TEMPERATURE = 0.3      # Niska — synteza musi być precyzyjna


# ---------------------------------------------------------------------------
# PROMPT NAUCZYCIELA
# ---------------------------------------------------------------------------

_TEACHER_SYSTEM_PROMPT = """\
Jesteś NEXUS TEACHER — zaawansowanym systemem syntezy wiedzy dla platformy cold-mail B2B.

Twoja rola: Analizujesz feedback operatora (oceny 1-5 + komentarze + poprawione wersje maili/leadów) \
i syntetyzujesz go w skondensowaną "Księgę Zasad" dla WSZYSTKICH agentów AI (Strategy, Scout, Researcher, Writer).

=== ALGORYTM SYNTEZY ===

1. DEDUPLIKACJA: Jeśli 3 feedbacki mówią to samo (np. "nie pisz o NFZ") — stwórz JEDNĄ \
absolutną regułę, nie trzy osobne zdania.

2. NADPISYWANIE: Jeśli nowa uwaga przeczy starej regule z obecnych wytycznych — \
NOWSZA uwaga (z bieżącego batcha) WYGRYWA. Zaznacz to w synthesis_reasoning.

3. KONDENSACJA: Zamień długie żale operatora na dyrektywy systemowe.
   Np. "Znowu ten głupi bot napisał o współpracy, a przecież mówiłem żeby tak nie robić" \
   → "[ZAKAZ]: Bezwzgl. zakaz słowa 'współpraca' — traktowane jako spam handlowy."

4. CONTRASTIVE EXTRACTION:
   - Ocena 4-5 z corrected_body → poprawiona wersja trafia do positive_examples
   - Ocena 4-5 bez poprawki → oryginalny mail trafia do positive_examples
   - Ocena 1-2 → oryginalny mail + POWÓD (z komentarza) trafia do negative_examples
   - Wybierz MAX 3 per kategoria, NAJBARDZIEJ różnorodne (różne branże/tony/podejścia)

5. PRIORYTETYZACJA: Reguły posortuj od najważniejszej (najczęściej powtarzana / najostrzej sformułowana).

=== FORMAT REGUŁ ===
Każda reguła to tag + dyrektywa:
- [ZAKAZ]: Bezwzględny zakaz czegoś
- [PRIORYTET]: Coś co MUSI być w każdym mailu/researchu
- [STYL]: Reguła dotycząca tonu/stylu
- [STRUKTURA]: Reguła dotycząca formatu/struktury

=== ROZSZERZONY ZASIĘG (4 AGENTY) ===
Oprócz research_guidelines i writing_guidelines, generujesz RÓWNIEŻ:

- strategy_guidelines — reguły dla Agenta Strategii (generowanie zapytań Google Maps).
  Jeśli operator narzeka na złe leady / złe branże / złe lokalizacje → sformułuj reguły strategiczne.
  Np. "[ZAKAZ]: Nie szukaj firm z branży X" lub "[PRIORYTET]: Więcej miast z regionu Y".
  Jeśli BRAK feedbacku dotyczącego strategii → zostaw PUSTE.

- scouting_guidelines — reguły dla Agenta Scouta (filtracja leadów).
  Jeśli operator narzeka na przepuszczanie złych leadów (scout_rating 1-2) → sformułuj reguły.
  Np. "[ZAKAZ]: Nie przepuszczaj firm jednoosobowych" lub "[PRIORYTET]: Przepuszczaj firmy z branży Y".
  Jeśli BRAK feedbacku dotyczącego scoutingu → zostaw PUSTE.

=== OGRANICZENIA ===
- Research guidelines: max 15 reguł
- Writing guidelines: max 20 reguł
- Strategy guidelines: max 10 reguł
- Scouting guidelines: max 10 reguł
- Nie powtarzaj reguł które są już wbudowane w system (np. "nie halucynuj" — to jest domyślne)
- Pisz po polsku, zwięźle, w formie dyrektyw systemowych
"""


# ---------------------------------------------------------------------------
# PUBLICZNE API
# ---------------------------------------------------------------------------

def run_teacher_synthesis(session: Session, client_id: int) -> dict:
    """
    Uruchamia pełny cykl syntezy wiedzy Teacher Agent.

    Returns:
        dict z kluczami: success, version, feedbacks_processed, reasoning
    """
    client = session.query(Client).filter(Client.id == client_id).first()
    if not client:
        logger.error(f"[TEACHER] Klient #{client_id} nie istnieje")
        return {"success": False, "error": "Klient nie istnieje"}

    # --- KROK A: Ingestion ---
    feedbacks = (
        session.query(LeadFeedback)
        .join(Lead, LeadFeedback.lead_id == Lead.id)
        .join(Campaign, Lead.campaign_id == Campaign.id)
        .filter(Campaign.client_id == client_id, LeadFeedback.is_processed == False)
        .all()
    )

    if not feedbacks:
        logger.info(f"[TEACHER] Klient #{client_id} ({client.name}) — brak nowych feedbacków")
        return {"success": True, "feedbacks_processed": 0, "reasoning": "Brak nowego feedbacku"}

    logger.info(
        f"[TEACHER] Klient #{client_id} ({client.name}) — "
        f"rozpoczynam syntezę z {len(feedbacks)} feedbacków"
    )

    # Pobierz obecny alignment (jeśli istnieje)
    current_alignment = session.query(ClientAlignment).filter_by(client_id=client_id).first()

    # --- Buduj kontekst feedbacku ---
    feedback_context = _build_feedback_context(session, feedbacks)
    current_rules_context = _build_current_rules_context(current_alignment)

    # --- KROK B+C: Synteza przez LLM ---
    human_prompt = f"""\
=== OBECNE REGUŁY (wersja {current_alignment.version if current_alignment else 0}) ===
{current_rules_context}

=== NOWY BATCH FEEDBACKU ({len(feedbacks)} ocen) ===
{feedback_context}

Przeprowadź syntezę. Pamiętaj: deduplikuj, nadpisuj konflikty (nowe wygrywa), kondensuj.
Wybierz top {_MAX_POSITIVE_EXAMPLES} pozytywne i top {_MAX_NEGATIVE_EXAMPLES} negatywne przykłady.
"""

    model_name = client.teacher_model or "gemini-3.1-pro-preview"
    try:
        teacher_llm = create_structured_llm(
            model_name,
            TeacherSynthesisOutput,
            temperature=_TEACHER_TEMPERATURE,
        )
        from langchain_core.messages import SystemMessage, HumanMessage
        result: TeacherSynthesisOutput = teacher_llm.invoke([
            SystemMessage(content=_TEACHER_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ])
    except Exception as e:
        logger.error(f"[TEACHER] Błąd LLM dla klienta #{client_id}: {e}", exc_info=True)
        return {"success": False, "error": f"Błąd LLM: {e}"}

    # --- KROK D: Archiwizacja starej wersji ---
    if current_alignment:
        _archive_alignment(session, current_alignment)

    # --- KROK E: Zapis nowej wersji ---
    new_version = (current_alignment.version + 1) if current_alignment else 1

    # Oblicz średnią ocenę w batchu
    ratings = []
    for fb in feedbacks:
        if fb.scout_rating:
            ratings.append(fb.scout_rating)
        if fb.writer_rating:
            ratings.append(fb.writer_rating)
        if fb.researcher_rating:
            ratings.append(fb.researcher_rating)
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    gold_examples = {
        "positive": [ex.model_dump() for ex in result.positive_examples[:_MAX_POSITIVE_EXAMPLES]],
        "negative": [ex.model_dump() for ex in result.negative_examples[:_MAX_NEGATIVE_EXAMPLES]],
    }

    if current_alignment:
        current_alignment.strategy_guidelines = result.strategy_guidelines or current_alignment.strategy_guidelines
        current_alignment.scouting_guidelines = result.scouting_guidelines or current_alignment.scouting_guidelines
        current_alignment.research_guidelines = result.research_guidelines
        current_alignment.writing_guidelines = result.writing_guidelines
        current_alignment.gold_examples = gold_examples
        current_alignment.version = new_version
        current_alignment.avg_rating_at_synthesis = avg_rating
        current_alignment.feedbacks_processed_count = (
            (current_alignment.feedbacks_processed_count or 0) + len(feedbacks)
        )
        current_alignment.last_updated = datetime.now(PL_TZ)
    else:
        new_alignment = ClientAlignment(
            client_id=client_id,
            strategy_guidelines=result.strategy_guidelines or "",
            scouting_guidelines=result.scouting_guidelines or "",
            research_guidelines=result.research_guidelines,
            writing_guidelines=result.writing_guidelines,
            gold_examples=gold_examples,
            version=new_version,
            avg_rating_at_synthesis=avg_rating,
            feedbacks_processed_count=len(feedbacks),
            last_updated=datetime.now(PL_TZ),
        )
        session.add(new_alignment)

    # --- Oznacz feedbacki jako przetworzone ---
    for fb in feedbacks:
        fb.is_processed = True

    session.commit()

    logger.info(
        f"[TEACHER] Synteza zakończona dla klienta #{client_id} ({client.name}) — "
        f"v{new_version}, {len(feedbacks)} feedbacków, avg_rating={avg_rating:.1f}"
    )

    return {
        "success": True,
        "version": new_version,
        "feedbacks_processed": len(feedbacks),
        "avg_rating": avg_rating,
        "reasoning": result.synthesis_reasoning,
    }


def check_and_run_teacher(session: Session, client_id: int, debounce_minutes: int = 30) -> dict | None:
    """
    Sprawdza czy są feedbacki do przetworzenia i czy minął debounce.
    Emergency mode: jeśli średnia ocena < 2.0 → natychmiastowa synteza.

    Returns:
        dict z wynikiem syntezy lub None jeśli nie uruchomiono.
    """
    # Sprawdź czy są nieprzetworzony feedback dla tego klienta
    pending = (
        session.query(LeadFeedback)
        .join(Lead, LeadFeedback.lead_id == Lead.id)
        .join(Campaign, Lead.campaign_id == Campaign.id)
        .filter(Campaign.client_id == client_id, LeadFeedback.is_processed == False)
    )

    count = pending.count()
    if count == 0:
        return None

    # Najnowszy feedback
    latest = pending.order_by(LeadFeedback.updated_at.desc()).first()
    if not latest or not latest.updated_at:
        return None

    now = datetime.now(PL_TZ)
    age_minutes = (now - latest.updated_at).total_seconds() / 60

    # Emergency mode — krytycznie niskie oceny
    ratings = []
    for fb in pending.all():
        if fb.writer_rating:
            ratings.append(fb.writer_rating)
        if fb.researcher_rating:
            ratings.append(fb.researcher_rating)

    avg = sum(ratings) / len(ratings) if ratings else 5.0
    is_emergency = avg < 2.0 and count >= 2

    if is_emergency:
        logger.warning(
            f"[TEACHER] EMERGENCY MODE klient #{client_id} — "
            f"avg_rating={avg:.1f}, {count} feedbacków. Natychmiastowa synteza!"
        )
        return run_teacher_synthesis(session, client_id)

    # Normalny debounce
    if age_minutes >= debounce_minutes:
        logger.info(
            f"[TEACHER] Debounce OK klient #{client_id} — "
            f"{count} feedbacków, najnowszy {age_minutes:.0f} min temu"
        )
        return run_teacher_synthesis(session, client_id)

    logger.debug(
        f"[TEACHER] Klient #{client_id} — {count} feedbacków czeka, "
        f"debounce {age_minutes:.0f}/{debounce_minutes} min"
    )
    return None


def rollback_alignment(session: Session, client_id: int, target_version: int | None = None) -> dict:
    """
    Cofnij ClientAlignment do poprzedniej wersji z AlignmentHistory.

    Args:
        target_version: Wersja do przywrócenia. None = ostatnia archiwalna.
    """
    if target_version:
        history = (
            session.query(AlignmentHistory)
            .filter_by(client_id=client_id, version=target_version)
            .first()
        )
    else:
        history = (
            session.query(AlignmentHistory)
            .filter_by(client_id=client_id)
            .order_by(AlignmentHistory.archived_at.desc())
            .first()
        )

    if not history:
        return {"success": False, "error": "Brak archiwalnej wersji do przywrócenia"}

    current = session.query(ClientAlignment).filter_by(client_id=client_id).first()
    if not current:
        return {"success": False, "error": "Brak aktualnego alignmentu"}

    # Archiwizuj obecną przed rollbackiem
    _archive_alignment(session, current)

    # Przywróć
    current.research_guidelines = history.research_guidelines
    current.writing_guidelines = history.writing_guidelines
    current.gold_examples = history.gold_examples
    current.version = current.version + 1  # Nowy numer, stara treść
    current.avg_rating_at_synthesis = history.avg_rating_at_synthesis
    current.last_updated = datetime.now(PL_TZ)

    session.commit()

    logger.info(
        f"[TEACHER] Rollback klient #{client_id} — "
        f"przywrócono v{history.version} jako v{current.version}"
    )

    return {
        "success": True,
        "restored_from_version": history.version,
        "new_version": current.version,
    }


# ---------------------------------------------------------------------------
# PRYWATNE HELPERY
# ---------------------------------------------------------------------------

def _build_feedback_context(session: Session, feedbacks: list[LeadFeedback]) -> str:
    """Buduje tekstowy kontekst z feedbacków do promptu Nauczyciela."""
    parts = []
    for i, fb in enumerate(feedbacks, 1):
        lead = session.query(Lead).filter(Lead.id == fb.lead_id).first()
        company = None
        if lead and lead.global_company_id:
            company = session.query(GlobalCompany).filter(GlobalCompany.id == lead.global_company_id).first()

        section = f"--- Feedback #{i} (Lead #{fb.lead_id}) ---\n"
        if company:
            section += f"Firma: {company.name} ({company.domain})\n"

        if fb.scout_rating:
            section += f"Ocena Scout (jakość leadu): {'★' * fb.scout_rating}{'☆' * (5 - fb.scout_rating)} ({fb.scout_rating}/5)\n"
        if fb.scout_comments:
            section += f"Komentarz Scout: {fb.scout_comments}\n"

        if fb.researcher_rating:
            section += f"Ocena Researcher: {'★' * fb.researcher_rating}{'☆' * (5 - fb.researcher_rating)} ({fb.researcher_rating}/5)\n"
        if fb.researcher_comments:
            section += f"Komentarz Researcher: {fb.researcher_comments}\n"

        if fb.writer_rating:
            section += f"Ocena Writer: {'★' * fb.writer_rating}{'☆' * (5 - fb.writer_rating)} ({fb.writer_rating}/5)\n"
        if fb.writer_comments:
            section += f"Komentarz Writer: {fb.writer_comments}\n"

        if lead and lead.generated_email_subject:
            section += f"Oryginalny temat: {lead.generated_email_subject}\n"
        if lead and lead.generated_email_body:
            body_preview = (lead.generated_email_body or "")[:500]
            section += f"Oryginalny mail:\n{body_preview}\n"

        if fb.corrected_subject:
            section += f"POPRAWIONY temat (operator): {fb.corrected_subject}\n"
        if fb.corrected_body:
            corrected_preview = (fb.corrected_body or "")[:500]
            section += f"POPRAWIONY mail (operator):\n{corrected_preview}\n"

        parts.append(section)

    return "\n".join(parts)


def _build_current_rules_context(alignment: ClientAlignment | None) -> str:
    """Buduje kontekst obecnych reguł do promptu Nauczyciela."""
    if not alignment:
        return "Brak obecnych reguł — to pierwsza synteza."

    parts = [f"Wersja: {alignment.version}"]

    if alignment.strategy_guidelines:
        parts.append(f"STRATEGY GUIDELINES:\n{alignment.strategy_guidelines}")
    if alignment.scouting_guidelines:
        parts.append(f"SCOUTING GUIDELINES:\n{alignment.scouting_guidelines}")
    if alignment.research_guidelines:
        parts.append(f"RESEARCH GUIDELINES:\n{alignment.research_guidelines}")
    if alignment.writing_guidelines:
        parts.append(f"WRITING GUIDELINES:\n{alignment.writing_guidelines}")

    if alignment.gold_examples:
        positives = alignment.gold_examples.get("positive", [])
        negatives = alignment.gold_examples.get("negative", [])
        if positives:
            parts.append(f"POZYTYWNE PRZYKŁADY ({len(positives)}):")
            for ex in positives:
                parts.append(f"  ✅ {ex.get('subject', '')} — {ex.get('reason', '')}")
        if negatives:
            parts.append(f"NEGATYWNE PRZYKŁADY ({len(negatives)}):")
            for ex in negatives:
                parts.append(f"  ❌ {ex.get('subject', '')} — {ex.get('reason', '')}")

    return "\n".join(parts)


def _archive_alignment(session: Session, alignment: ClientAlignment) -> None:
    """Archiwizuje snapshot alignmentu. Utrzymuje max _MAX_HISTORY_VERSIONS per klient."""
    archive = AlignmentHistory(
        client_id=alignment.client_id,
        version=alignment.version,
        research_guidelines=alignment.research_guidelines,
        writing_guidelines=alignment.writing_guidelines,
        gold_examples=alignment.gold_examples,
        avg_rating_at_synthesis=alignment.avg_rating_at_synthesis,
        archived_at=datetime.now(PL_TZ),
    )
    session.add(archive)

    # FIFO — usuń najstarsze jeśli > limit
    old_versions = (
        session.query(AlignmentHistory)
        .filter_by(client_id=alignment.client_id)
        .order_by(AlignmentHistory.archived_at.desc())
        .offset(_MAX_HISTORY_VERSIONS)
        .all()
    )
    for old in old_versions:
        session.delete(old)
