# app/stats_manager.py
"""
NEXUS STATISTICS ENGINE — Atomowe metryki dzienne z UPSERT.

Każda funkcja increment_*() wykonuje:
1. INSERT wiersza z dzisiejszą datą jeśli nie istnieje
2. Atomowy UPDATE (inkrementacja) konkretnej kolumny
3. Przeliczanie reply_rate i positive_rate

Payload CMS backend czyta tabelę campaign_statistics bezpośrednio z bazy.
"""

import logging
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import CampaignStatistics

logger = logging.getLogger("nexus_stats")


# ---------------------------------------------------------------------------
# PRYWATNY HELPER: UPSERT (atomowy)
# ---------------------------------------------------------------------------

def _upsert_increment(session: Session, client_id: int, column: str, count: int = 1) -> None:
    """
    Atomowy UPSERT: wstaw wiersz z dzisiejszą datą jeśli brak,
    a zawsze inkrementuj podaną kolumnę o count.
    Używa raw SQL z ON CONFLICT DO UPDATE (PostgreSQL).
    """
    today = date.today()
    
    sql = text(f"""
        INSERT INTO campaign_statistics (client_id, date, {column})
        VALUES (:client_id, :today, :count)
        ON CONFLICT ON CONSTRAINT uq_client_date
        DO UPDATE SET {column} = COALESCE(campaign_statistics.{column}, 0) + :count
    """)
    
    try:
        session.execute(sql, {"client_id": client_id, "today": today, "count": count})
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"[STATS] Błąd UPSERT ({column}, client={client_id}): {e}")


def _recalc_rates(session: Session, client_id: int) -> None:
    """Przelicza reply_rate i positive_rate dla dzisiejszego wiersza."""
    today = date.today()
    sql = text("""
        UPDATE campaign_statistics
        SET reply_rate = CASE WHEN emails_sent > 0 
                              THEN ROUND((replies_total::numeric / emails_sent) * 100, 2)
                              ELSE 0 END,
            positive_rate = CASE WHEN replies_total > 0
                                 THEN ROUND((replies_positive::numeric / replies_total) * 100, 2)
                                 ELSE 0 END
        WHERE client_id = :client_id AND date = :today
    """)
    try:
        session.execute(sql, {"client_id": client_id, "today": today})
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"[STATS] Błąd recalc rates (client={client_id}): {e}")


# ---------------------------------------------------------------------------
# PUBLICZNE API — SCOUTING
# ---------------------------------------------------------------------------

def increment_scanned(session: Session, client_id: int, count: int = 1) -> None:
    """Domeny przeskanowane przez Scout (surowe wyniki Apify)."""
    _upsert_increment(session, client_id, "domains_scanned", count)

def increment_approved(session: Session, client_id: int, count: int = 1) -> None:
    """Domeny przepuszczone przez AI Gatekeeper."""
    _upsert_increment(session, client_id, "domains_approved", count)

def increment_rejected(session: Session, client_id: int, count: int = 1) -> None:
    """Domeny odrzucone przez AI Gatekeeper."""
    _upsert_increment(session, client_id, "domains_rejected", count)

def increment_blacklisted(session: Session, client_id: int, count: int = 1) -> None:
    """Domeny zablokowane przez RODO blacklist."""
    _upsert_increment(session, client_id, "domains_blacklisted", count)


# ---------------------------------------------------------------------------
# PUBLICZNE API — RESEARCH
# ---------------------------------------------------------------------------

def increment_analyzed(session: Session, client_id: int, count: int = 1) -> None:
    """Lead przeanalizowany przez Researcher (Firecrawl)."""
    _upsert_increment(session, client_id, "leads_analyzed", count)

def increment_emails_found(session: Session, client_id: int, count: int = 1) -> None:
    """Adresy email wyłuskane ze stron."""
    _upsert_increment(session, client_id, "emails_found", count)

def increment_verified(session: Session, client_id: int, count: int = 1) -> None:
    """Adresy email zweryfikowane (MX/DeBounce)."""
    _upsert_increment(session, client_id, "emails_verified", count)

def increment_freemail_rejected(session: Session, client_id: int, count: int = 1) -> None:
    """Adresy odrzucone jako freemail (bramka B2B)."""
    _upsert_increment(session, client_id, "emails_rejected_freemail", count)


# ---------------------------------------------------------------------------
# PUBLICZNE API — WRITING
# ---------------------------------------------------------------------------

def increment_drafted(session: Session, client_id: int, count: int = 1, confidence_score: float = 0.0) -> None:
    """Draft wygenerowany przez Writer."""
    _upsert_increment(session, client_id, "emails_drafted", count)
    if confidence_score > 0:
        # Aktualizujemy średnią (przybliżona — running average)
        today = date.today()
        sql = text("""
            UPDATE campaign_statistics
            SET avg_confidence_score = CASE 
                WHEN emails_drafted > 0 
                THEN ROUND(((avg_confidence_score * (emails_drafted - :count)) + (:score * :count))::numeric / emails_drafted, 1)
                ELSE :score END
            WHERE client_id = :client_id AND date = :today
        """)
        try:
            session.execute(sql, {"client_id": client_id, "today": today, "count": count, "score": confidence_score})
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"[STATS] Błąd avg_confidence (client={client_id}): {e}")


# ---------------------------------------------------------------------------
# PUBLICZNE API — DELIVERY
# ---------------------------------------------------------------------------

def increment_sent(session: Session, client_id: int, count: int = 1, step: int = 1) -> None:
    """Email wysłany (SMTP) lub zapisany (IMAP draft)."""
    _upsert_increment(session, client_id, "emails_sent", count)
    if step == 2:
        _upsert_increment(session, client_id, "followup_step_2_sent", count)
    elif step >= 3:
        _upsert_increment(session, client_id, "followup_step_3_sent", count)
    _recalc_rates(session, client_id)

def increment_bounce(session: Session, client_id: int, count: int = 1) -> None:
    """Zwrotka (BOUNCED)."""
    _upsert_increment(session, client_id, "bounces", count)

def increment_dns_block(session: Session, client_id: int, count: int = 1) -> None:
    """Blokada DNS (brak SPF/DMARC)."""
    _upsert_increment(session, client_id, "dns_blocks", count)


# ---------------------------------------------------------------------------
# PUBLICZNE API — ENGAGEMENT
# ---------------------------------------------------------------------------

def increment_reply(session: Session, client_id: int, sentiment: str = "NEUTRAL") -> None:
    """Odpowiedź od leada. Sentiment: POSITIVE, NEGATIVE, NEUTRAL."""
    _upsert_increment(session, client_id, "replies_total", 1)
    
    if sentiment == "POSITIVE":
        _upsert_increment(session, client_id, "replies_positive", 1)
    elif sentiment == "NEGATIVE":
        _upsert_increment(session, client_id, "replies_negative", 1)
    else:
        _upsert_increment(session, client_id, "replies_neutral", 1)
    
    _recalc_rates(session, client_id)

def increment_optout(session: Session, client_id: int, count: int = 1) -> None:
    """Żądanie wypisania 'Wypisz'."""
    _upsert_increment(session, client_id, "opt_outs", count)

def record_response_time(session: Session, client_id: int, hours: float) -> None:
    """Rejestruje czas odpowiedzi w godzinach (running average)."""
    today = date.today()
    sql = text("""
        UPDATE campaign_statistics
        SET avg_response_time_hours = CASE 
            WHEN avg_response_time_hours IS NULL THEN :hours
            WHEN replies_total > 0 
            THEN ROUND(((avg_response_time_hours * (replies_total - 1)) + :hours)::numeric / replies_total, 1)
            ELSE :hours END
        WHERE client_id = :client_id AND date = :today
    """)
    try:
        session.execute(sql, {"client_id": client_id, "today": today, "hours": hours})
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"[STATS] Błąd response time (client={client_id}): {e}")


# ---------------------------------------------------------------------------
# PUBLICZNE API — ODCZYT (dla Payload CMS i GUI)
# ---------------------------------------------------------------------------

def get_daily_stats(session: Session, client_id: int, target_date: date = None) -> dict:
    """Zwraca statystyki z danego dnia (domyślnie dzisiaj)."""
    target_date = target_date or date.today()
    row = session.query(CampaignStatistics).filter(
        CampaignStatistics.client_id == client_id,
        CampaignStatistics.date == target_date,
    ).first()
    
    if not row:
        return {}
    
    return {c.key: getattr(row, c.key) for c in CampaignStatistics.__table__.columns if c.key != "id"}


def get_range_stats(session: Session, client_id: int, from_date: date, to_date: date) -> list:
    """Zwraca statystyki z zakresu dat (lista słowników dziennych)."""
    rows = session.query(CampaignStatistics).filter(
        CampaignStatistics.client_id == client_id,
        CampaignStatistics.date >= from_date,
        CampaignStatistics.date <= to_date,
    ).order_by(CampaignStatistics.date).all()
    
    return [
        {c.key: getattr(row, c.key) for c in CampaignStatistics.__table__.columns if c.key != "id"}
        for row in rows
    ]


    where_clause = "WHERE client_id = :client_id" if client_id != 0 else ""
    sql = text(f"""
        SELECT
            COALESCE(SUM(domains_scanned), 0) AS domains_scanned,
            COALESCE(SUM(domains_approved), 0) AS domains_approved,
            COALESCE(SUM(domains_rejected), 0) AS domains_rejected,
            COALESCE(SUM(domains_blacklisted), 0) AS domains_blacklisted,
            COALESCE(SUM(leads_analyzed), 0) AS leads_analyzed,
            COALESCE(SUM(emails_found), 0) AS emails_found,
            COALESCE(SUM(emails_verified), 0) AS emails_verified,
            COALESCE(SUM(emails_rejected_freemail), 0) AS emails_rejected_freemail,
            COALESCE(SUM(emails_drafted), 0) AS emails_drafted,
            COALESCE(SUM(emails_sent), 0) AS emails_sent,
            COALESCE(SUM(followup_step_2_sent), 0) AS followup_step_2_sent,
            COALESCE(SUM(followup_step_3_sent), 0) AS followup_step_3_sent,
            COALESCE(SUM(bounces), 0) AS bounces,
            COALESCE(SUM(dns_blocks), 0) AS dns_blocks,
            COALESCE(SUM(replies_total), 0) AS replies_total,
            COALESCE(SUM(replies_positive), 0) AS replies_positive,
            COALESCE(SUM(replies_negative), 0) AS replies_negative,
            COALESCE(SUM(replies_neutral), 0) AS replies_neutral,
            COALESCE(SUM(opt_outs), 0) AS opt_outs,
            ROUND(AVG(avg_confidence_score)::numeric, 1) AS avg_confidence_score,
            ROUND(AVG(avg_response_time_hours)::numeric, 1) AS avg_response_time_hours,
            CASE WHEN SUM(emails_sent) > 0 
                 THEN ROUND((SUM(replies_total)::numeric / SUM(emails_sent)) * 100, 2)
                 ELSE 0 END AS reply_rate,
            CASE WHEN SUM(replies_total) > 0
                 THEN ROUND((SUM(replies_positive)::numeric / SUM(replies_total)) * 100, 2)
                 ELSE 0 END AS positive_rate
        FROM campaign_statistics
        {where_clause}
    """)
    
    result = session.execute(sql, {"client_id": client_id}).mappings().first()
    return dict(result) if result else {}
