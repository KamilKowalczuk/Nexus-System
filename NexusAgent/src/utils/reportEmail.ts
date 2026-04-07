/**
 * reportEmail.ts
 * ────────────────────────────────────────────────────────────────────
 * Premium HTML email template for campaign statistics reports.
 * Sent via Resend with PDF attachment.
 *
 * Design: NEXUS dark theme — consistent with invoice/onboarding emails.
 * ────────────────────────────────────────────────────────────────────
 */

import { Resend } from 'resend';
import type { AllTimeStats, WeekComparison } from './campaignStats';

const SITE_URL = 'https://nexusagent.pl';

interface ReportEmailParams {
  toEmail: string;
  companyName: string;
  orderNumber: string;
  summary: AllTimeStats;
  weekComparison: WeekComparison;
  reportPeriod: string;
  pdfBuffer: Buffer;
}

function buildKpiCell(value: string, label: string, color: string): string {
  return `
    <td style="padding:8px;text-align:center;width:25%;">
      <div style="font-size:24px;font-weight:800;color:${color};font-family:'JetBrains Mono',monospace;line-height:1.2;">${value}</div>
      <div style="font-size:9px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;margin-top:4px;">${label}</div>
    </td>`;
}

function trendArrow(thisWeek: number, lastWeek: number): string {
  if (lastWeek === 0 && thisWeek === 0) return '<span style="color:#64748b;">—</span>';
  const change = lastWeek > 0 ? ((thisWeek - lastWeek) / lastWeek * 100) : 100;
  if (change > 0) return `<span style="color:#22c55e;">+ ${Math.abs(change).toFixed(0)}%</span>`;
  if (change < 0) return `<span style="color:#ef4444;">- ${Math.abs(change).toFixed(0)}%</span>`;
  return '<span style="color:#64748b;">— 0%</span>';
}

function buildReportEmail(params: ReportEmailParams): { subject: string; html: string } {
  const { companyName, orderNumber, summary: s, weekComparison: wk, reportPeriod } = params;

  const fmt = (n: any) => Number(n ?? 0).toLocaleString('pl-PL');
  const fmtPct = (n: any) => `${Number(n ?? 0).toFixed(1)}%`;

  return {
    subject: `NEXUS Agent – Raport Kampanii · ${companyName} · ${reportPeriod}`,
    html: `
<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NEXUS Agent – Raport Kampanii</title>
</head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter','Segoe UI',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
              <img
                src="${SITE_URL}/logo.webp"
                alt="NEXUS Agent"
                width="100"
                height="100"
                style="display:block;margin:0 auto 12px auto;"
              />
              <div style="font-family:monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;margin-bottom:8px;">Dział Analityki Kampanii</div>
              <div style="font-size:26px;font-weight:900;text-transform:uppercase;letter-spacing:-0.02em;color:#fff;">Raport Kampanii</div>
            </td>
          </tr>

          <!-- Main content -->
          <tr>
            <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">

              <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#0ceaed;margin-bottom:16px;">Status: Kampania Aktywna</div>

              <h1 style="margin:0 0 8px;font-size:22px;font-weight:800;text-transform:uppercase;letter-spacing:-0.02em;color:#fff;line-height:1.2;">
                ${companyName}
              </h1>
              <p style="margin:0 0 24px;color:#94a3b8;font-size:13px;line-height:1.6;">
                Raport za okres <strong style="color:#fff;">${reportPeriod}</strong> · Zamówienie: <strong style="color:#a855f7;">${orderNumber}</strong>
              </p>

              <!-- KPI Cards Row 1 -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:16px;margin-bottom:16px;">
                <tr>
                  ${buildKpiCell(fmt(s.total_first_touch), 'Wysłane', '#0ceaed')}
                  ${buildKpiCell(fmt(s.total_replies), 'Odpowiedzi', '#a855f7')}
                  ${buildKpiCell(fmt(s.hot_leads), 'Leady', '#22c55e')}
                  ${buildKpiCell(fmtPct(s.reply_rate), 'Wskaźnik ODP.', '#f59e0b')}
                </tr>
              </table>

              <!-- KPI Cards Row 2 -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:16px;margin-bottom:24px;">
                <tr>
                  ${buildKpiCell(fmt(s.total_scanned), 'Skanowanie', '#0ceaed')}
                  ${buildKpiCell(fmt(s.total_delivery), 'Dostarczone', '#a855f7')}
                  ${buildKpiCell(fmtPct(s.positive_rate), 'Konwersja ODP.', '#22c55e')}
                  ${buildKpiCell(`${s.avg_response_hours || 0}h`, 'Średni ODP.', '#f59e0b')}
                </tr>
              </table>

              <!-- Week comparison -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(12,234,237,0.04);border:1px solid rgba(12,234,237,0.15);border-radius:12px;padding:16px;margin-bottom:24px;">
                <tr>
                  <td colspan="3">
                    <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#0ceaed;margin-bottom:10px;">[>] Trend Tygodniowy</div>
                  </td>
                </tr>
                <tr>
                  <td style="padding:6px 12px;text-align:center;">
                    <div style="font-size:9px;font-family:monospace;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Wysłane</div>
                    <div style="font-size:16px;font-weight:700;color:#fff;">${fmt(wk.this_week.sent)}</div>
                    <div style="font-size:10px;margin-top:2px;">${trendArrow(wk.this_week.sent, wk.last_week.sent)}</div>
                  </td>
                  <td style="padding:6px 12px;text-align:center;">
                    <div style="font-size:9px;font-family:monospace;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Odpowiedzi</div>
                    <div style="font-size:16px;font-weight:700;color:#fff;">${fmt(wk.this_week.replies)}</div>
                    <div style="font-size:10px;margin-top:2px;">${trendArrow(wk.this_week.replies, wk.last_week.replies)}</div>
                  </td>
                  <td style="padding:6px 12px;text-align:center;">
                    <div style="font-size:9px;font-family:monospace;color:#64748b;text-transform:uppercase;margin-bottom:4px;">🔥 Leady</div>
                    <div style="font-size:16px;font-weight:700;color:#22c55e;">${fmt(wk.this_week.hot_leads)}</div>
                    <div style="font-size:10px;margin-top:2px;">${trendArrow(wk.this_week.hot_leads, wk.last_week.hot_leads)}</div>
                  </td>
                </tr>
              </table>

              <!-- Insights -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(168,85,247,0.05);border:1px solid rgba(168,85,247,0.2);border-radius:12px;padding:16px;margin-bottom:24px;">
                <tr>
                  <td>
                    <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#a855f7;margin-bottom:10px;">[i] Kluczowe Obserwacje</div>
                    <div style="font-size:12px;color:#cbd5e1;line-height:1.8;">
                      ${Number(s.reply_rate) >= 5
                        ? `[+] Wskaźnik odpowiedzi ${fmtPct(s.reply_rate)} — w normie rynkowej lub powyżej (benchmark: 5-15%)<br/>`
                        : Number(s.reply_rate) > 0
                        ? `[!] Wskaźnik odpowiedzi ${fmtPct(s.reply_rate)} — optymalizujemy personalizację<br/>`
                        : ''}
                      ${s.hot_leads > 0 ? `[!] ${s.hot_leads} gorących leadów czeka na domknięcie w Twojej skrzynce<br/>` : ''}
                      ${Number(s.bounce_rate) < 3 ? `[+] Bounce rate ${fmtPct(s.bounce_rate)} — domena bezpieczna<br/>` : ''}
                      ${Number(s.avg_ai_quality) >= 70 ? `[+] Jakość treści AI: ${s.avg_ai_quality}/100<br/>` : ''}
                      [i] Łącznie dostarczono ${fmt(s.total_delivery)} wiadomości w analizowanym okresie
                    </div>
                  </td>
                </tr>
              </table>

              <!-- CTA -->
              <div style="text-align:center;margin-bottom:16px;">
                <div style="font-size:11px;color:#64748b;margin-bottom:12px;">Pełny raport (wykresy, tabele dzienne, metryki AI) znajdziesz w załączniku PDF.</div>
              </div>

              <!-- Security -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(168,85,247,0.03);border:1px solid rgba(168,85,247,0.12);border-radius:8px;padding:12px;">
                <tr>
                  <td>
                    <div style="font-size:9px;font-family:monospace;color:#a855f7;letter-spacing:0.1em;">[#] RAPORT POUFNY</div>
                    <div style="font-size:10px;color:#475569;margin-top:4px;">Ten raport został wygenerowany systemowo. Dane są przeznaczone wyłącznie dla odbiorcy.</div>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;text-align:center;">
              <div style="margin-bottom:12px;">
                <a href="${SITE_URL}/dokumenty/regulamin" style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;text-decoration:none;margin:0 8px;">Regulamin</a>
                <span style="color:#1e293b;">·</span>
                <a href="${SITE_URL}/dokumenty/polityka-prywatnosci" style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;text-decoration:none;margin:0 8px;">Polityka Prywatności</a>
              </div>
              <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#334155;">
                © ${new Date().getFullYear()} NEXUS SYSTEMS · nexusagent.pl · Raporty: raport@nexusagent.pl
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `,
  };
}

/**
 * Wysyła email z raportem kampanii + PDF w załączniku przez Resend.
 */
export async function dispatchReportEmail(params: ReportEmailParams): Promise<boolean> {
  const resendKey = import.meta.env.RESEND_API_KEY || process.env.RESEND_API_KEY;

  if (!resendKey) {
    console.error('[Resend/Report] Brak RESEND_API_KEY w zmiennych środowiskowych.');
    return false;
  }

  const resend = new Resend(resendKey);
  const { subject, html } = buildReportEmail(params);

  const safeName = params.companyName
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, '')
    .trim()
    .replace(/ +/g, '-')
    .slice(0, 40) || 'klient';

  const dateStr = new Date().toISOString().slice(0, 10);

  try {
    const result = await resend.emails.send({
      from: 'NEXUS Agent <raport@nexusagent.pl>',
      to: params.toEmail,
      subject,
      html,
      attachments: [
        {
          filename: `nexus-raport-${safeName}-${dateStr}.pdf`,
          content: params.pdfBuffer,
        },
      ],
    });

    if (result.error) {
      console.error('[Resend/Report] Błąd wysyłki:', result.error);
      return false;
    }

    console.log(`[Resend/Report] Raport wysłany do ${params.toEmail} (${params.companyName})`);
    return true;
  } catch (err) {
    console.error('[Resend/Report] Nieoczekiwany wyjątek:', err);
    return false;
  }
}
