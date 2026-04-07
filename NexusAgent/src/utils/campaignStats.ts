/**
 * campaignStats.ts
 * ────────────────────────────────────────────────────────────────────
 * Bezpośrednie query SQL do tabel bota (clients + campaign_statistics)
 * na tej samej bazie PostgreSQL (Railway) co Payload CMS.
 *
 * Relacja: orders.id ──→ clients.payload_order_id ──→ campaign_statistics.client_id
 * ────────────────────────────────────────────────────────────────────
 */

import pg from 'pg';
const { Pool } = pg;

let pool: InstanceType<typeof Pool> | null = null;

function getPool(): InstanceType<typeof Pool> {
  if (!pool) {
    const connectionString =
      import.meta.env.DATABASE_URL ||
      process.env.DATABASE_URL ||
      '';

    if (!connectionString) {
      throw new Error('[CampaignStats] Brak DATABASE_URL w zmiennych środowiskowych.');
    }

    pool = new Pool({
      connectionString,
      max: 5,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
      ssl: connectionString.includes('railway') ? { rejectUnauthorized: false } : undefined,
    });
  }
  return pool;
}

// ─── Interfejsy ──────────────────────────────────────────────────────────

export interface DailyStats {
  date: string;
  // Scouting
  domains_scanned: number;
  domains_approved: number;
  domains_rejected: number;
  // Research
  leads_analyzed: number;
  emails_found: number;
  emails_verified: number;
  emails_rejected_freemail: number;
  // Writing
  emails_drafted: number;
  avg_confidence_score: number;
  // Delivery
  emails_sent: number;
  followup_step_2_sent: number;
  followup_step_3_sent: number;
  bounces: number;
  // Engagement
  replies_total: number;
  replies_positive: number;
  replies_negative: number;
  replies_neutral: number;
  opt_outs: number;
  // Performance
  avg_response_time_hours: number;
  reply_rate: number;
}

export interface AllTimeStats {
  active_days: number;
  total_scanned: number;
  total_qualified: number;
  total_first_touch: number;
  total_followup2: number;
  total_followup3: number;
  total_delivery: number;
  total_replies: number;
  hot_leads: number;
  total_optouts: number;
  total_bounces: number;
  total_drafted: number;
  total_emails_found: number;
  total_emails_verified: number;
  avg_ai_quality: number;
  avg_response_hours: number;
  reply_rate: number;
  positive_rate: number;
  bounce_rate: number;
  scout_approval_rate: number;
  email_verification_rate: number;
}

export interface WeekComparison {
  this_week: { sent: number; replies: number; hot_leads: number };
  last_week: { sent: number; replies: number; hot_leads: number };
}

export interface ClientInfo {
  id: number;
  payload_order_id: number;
  payload_brief_id: number | null;
  company_name: string | null;
}

// ─── Query: Dane dzienne (ostatnie 30 dni do wykresów) ──────────────────

export async function getLast30DaysStats(orderId: number | string): Promise<DailyStats[]> {
  const db = getPool();
  const { rows } = await db.query<DailyStats>(
    `SELECT 
       cs.date::text AS date,
       COALESCE(cs.domains_scanned, 0) AS domains_scanned,
       COALESCE(cs.domains_approved, 0) AS domains_approved,
       COALESCE(cs.domains_rejected, 0) AS domains_rejected,
       COALESCE(cs.leads_analyzed, 0) AS leads_analyzed,
       COALESCE(cs.emails_found, 0) AS emails_found,
       COALESCE(cs.emails_verified, 0) AS emails_verified,
       COALESCE(cs.emails_rejected_freemail, 0) AS emails_rejected_freemail,
       COALESCE(cs.emails_drafted, 0) AS emails_drafted,
       COALESCE(cs.avg_confidence_score, 0) AS avg_confidence_score,
       COALESCE(cs.emails_sent, 0) AS emails_sent,
       COALESCE(cs.followup_step_2_sent, 0) AS followup_step_2_sent,
       COALESCE(cs.followup_step_3_sent, 0) AS followup_step_3_sent,
       COALESCE(cs.bounces, 0) AS bounces,
       COALESCE(cs.replies_total, 0) AS replies_total,
       COALESCE(cs.replies_positive, 0) AS replies_positive,
       COALESCE(cs.replies_negative, 0) AS replies_negative,
       COALESCE(cs.replies_neutral, 0) AS replies_neutral,
       COALESCE(cs.opt_outs, 0) AS opt_outs,
       COALESCE(cs.avg_response_time_hours, 0) AS avg_response_time_hours,
       COALESCE(cs.reply_rate, 0) AS reply_rate
     FROM campaign_statistics cs
     JOIN clients c ON c.id = cs.client_id
     WHERE c.payload_order_id = $1
       AND cs.date >= CURRENT_DATE - INTERVAL '30 days'
     ORDER BY cs.date ASC`,
    [orderId]
  );
  return rows;
}

// ─── Query: Podsumowanie all-time / 30 dni (KPI cards) ──────────────────

export async function getSummaryStats(orderId: number | string, days: number = 30): Promise<AllTimeStats | null> {
  const db = getPool();
  const interval = days > 0 ? `AND cs.date >= CURRENT_DATE - INTERVAL '${days} days'` : '';

  const { rows } = await db.query(
    `SELECT 
       COUNT(*)::int AS active_days,
       COALESCE(SUM(cs.domains_scanned), 0)::int AS total_scanned,
       COALESCE(SUM(cs.domains_approved), 0)::int AS total_qualified,
       COALESCE(SUM(cs.emails_sent), 0)::int AS total_first_touch,
       COALESCE(SUM(cs.followup_step_2_sent), 0)::int AS total_followup2,
       COALESCE(SUM(cs.followup_step_3_sent), 0)::int AS total_followup3,
       (COALESCE(SUM(cs.emails_sent), 0) + COALESCE(SUM(cs.followup_step_2_sent), 0) + COALESCE(SUM(cs.followup_step_3_sent), 0))::int AS total_delivery,
       COALESCE(SUM(cs.replies_total), 0)::int AS total_replies,
       COALESCE(SUM(cs.replies_positive), 0)::int AS hot_leads,
       COALESCE(SUM(cs.opt_outs), 0)::int AS total_optouts,
       COALESCE(SUM(cs.bounces), 0)::int AS total_bounces,
       COALESCE(SUM(cs.emails_drafted), 0)::int AS total_drafted,
       COALESCE(SUM(cs.emails_found), 0)::int AS total_emails_found,
       COALESCE(SUM(cs.emails_verified), 0)::int AS total_emails_verified,
       ROUND(AVG(NULLIF(cs.avg_confidence_score, 0))::numeric, 1) AS avg_ai_quality,
       ROUND(AVG(NULLIF(cs.avg_response_time_hours, 0))::numeric, 1) AS avg_response_hours,
       CASE WHEN SUM(cs.emails_sent) > 0 
            THEN ROUND((SUM(cs.replies_total)::numeric / SUM(cs.emails_sent)) * 100, 2) 
            ELSE 0 END AS reply_rate,
       CASE WHEN SUM(cs.replies_total) > 0 
            THEN ROUND((SUM(cs.replies_positive)::numeric / SUM(cs.replies_total)) * 100, 2) 
            ELSE 0 END AS positive_rate,
       CASE WHEN SUM(cs.emails_sent) > 0 
            THEN ROUND((SUM(cs.bounces)::numeric / SUM(cs.emails_sent)) * 100, 2) 
            ELSE 0 END AS bounce_rate,
       CASE WHEN SUM(cs.domains_scanned) > 0 
            THEN ROUND((SUM(cs.domains_approved)::numeric / SUM(cs.domains_scanned)) * 100, 2)
            ELSE 0 END AS scout_approval_rate,
       CASE WHEN SUM(cs.emails_found) > 0 
            THEN ROUND((SUM(cs.emails_verified)::numeric / SUM(cs.emails_found)) * 100, 2) 
            ELSE 0 END AS email_verification_rate
     FROM campaign_statistics cs
     JOIN clients c ON c.id = cs.client_id
     WHERE c.payload_order_id = $1
       ${interval}`,
    [orderId]
  );

  if (!rows.length || rows[0].active_days === 0) return null;
  return rows[0] as AllTimeStats;
}

// ─── Query: Porównanie tydzień do tygodnia ──────────────────────────────

export async function getWeekComparison(orderId: number | string): Promise<WeekComparison> {
  const db = getPool();
  const { rows } = await db.query(
    `SELECT 
       CASE WHEN cs.date >= CURRENT_DATE - INTERVAL '7 days' THEN 'this_week'
            ELSE 'last_week' END AS period,
       COALESCE(SUM(cs.emails_sent), 0)::int AS sent,
       COALESCE(SUM(cs.replies_total), 0)::int AS replies,
       COALESCE(SUM(cs.replies_positive), 0)::int AS hot_leads
     FROM campaign_statistics cs
     JOIN clients c ON c.id = cs.client_id
     WHERE c.payload_order_id = $1
       AND cs.date >= CURRENT_DATE - INTERVAL '14 days'
     GROUP BY period`,
    [orderId]
  );

  const result: WeekComparison = {
    this_week: { sent: 0, replies: 0, hot_leads: 0 },
    last_week: { sent: 0, replies: 0, hot_leads: 0 },
  };

  for (const row of rows) {
    if (row.period === 'this_week') {
      result.this_week = { sent: row.sent, replies: row.replies, hot_leads: row.hot_leads };
    } else {
      result.last_week = { sent: row.sent, replies: row.replies, hot_leads: row.hot_leads };
    }
  }

  return result;
}

// ─── Query: Info o kliencie z tabeli bota ────────────────────────────────

export async function getClientInfo(orderId: number | string): Promise<ClientInfo | null> {
  const db = getPool();
  const { rows } = await db.query<ClientInfo>(
    `SELECT id, payload_order_id, payload_brief_id, company_name
     FROM clients
     WHERE payload_order_id = $1
     LIMIT 1`,
    [orderId]
  );
  return rows[0] || null;
}

// ─── Sprawdź czy klient ma jakiekolwiek statystyki ──────────────────────

export async function hasAnyStats(orderId: number | string): Promise<boolean> {
  const db = getPool();
  const { rows } = await db.query(
    `SELECT 1 FROM campaign_statistics cs
     JOIN clients c ON c.id = cs.client_id
     WHERE c.payload_order_id = $1
     LIMIT 1`,
    [orderId]
  );
  return rows.length > 0;
}
