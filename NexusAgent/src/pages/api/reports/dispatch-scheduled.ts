/**
 * /api/reports/dispatch-scheduled.ts
 * ────────────────────────────────────────────────────────────────────
 * Endpoint wywoływany co 24h przez external cron (cron-job.org / Railway).
 * Sprawdza które zamówienia wymagają raportu (co 3 dni od briefu)
 * i wysyła im premium raport statystyk.
 *
 * POST / GET z nagłówkiem Authorization: Bearer CRON_SECRET
 * ────────────────────────────────────────────────────────────────────
 */

import type { APIRoute } from 'astro';
import { getSummaryStats, getLast30DaysStats, getWeekComparison, hasAnyStats } from '../../../utils/campaignStats';
import { generateReportPdf } from '../../../utils/reportPdf';
import { dispatchReportEmail } from '../../../utils/reportEmail';

export const prerender = false;

const REPORT_INTERVAL_DAYS = 3;

async function handleDispatch(request: Request): Promise<Response> {
  // ─── Auth: CRON_SECRET ───
  const cronSecret = import.meta.env.CRON_SECRET || process.env.CRON_SECRET;
  if (!cronSecret) {
    console.error('[Cron/Reports] CRON_SECRET nie ustawiony.');
    return new Response(JSON.stringify({ error: 'Serwer nie skonfigurowany.' }), {
      status: 503, headers: { 'Content-Type': 'application/json' },
    });
  }

  const authHeader = request.headers.get('authorization') || '';
  const providedSecret =
    authHeader.replace(/^Bearer\s+/i, '') ||
    new URL(request.url).searchParams.get('secret') || '';

  if (providedSecret !== cronSecret) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401, headers: { 'Content-Type': 'application/json' },
    });
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  const authHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) authHeaders['Authorization'] = `users API-Key ${apiKey}`;

  try {
    // 1. Pobierz wszystkie aktywne zamówienia z briefem
    const ordersRes = await fetch(
      `${payloadUrl}/api/orders?where[subscriptionStatus][equals]=active&where[brief][exists]=true&limit=100&depth=1`,
      { headers: authHeaders }
    );

    if (!ordersRes.ok) {
      console.error('[Cron/Reports] Nie można pobrać zamówień:', ordersRes.status);
      return new Response(JSON.stringify({ error: 'Błąd pobierania zamówień' }), {
        status: 500, headers: { 'Content-Type': 'application/json' },
      });
    }

    const ordersData = await ordersRes.json();
    const orders = ordersData.docs || [];

    const now = new Date();
    const intervalMs = REPORT_INTERVAL_DAYS * 24 * 60 * 60 * 1000;
    const results: Array<{ orderId: string; email: string; status: string }> = [];

    for (const order of orders) {
      const orderId = order.id;
      const email = order.customerEmail;

      if (!email) {
        results.push({ orderId, email: '—', status: 'brak_emaila' });
        continue;
      }

      // Sprawdź czy minęło 3 dni od ostatniego raportu
      const lastSent = order.lastReportSentAt ? new Date(order.lastReportSentAt) : null;
      if (lastSent && (now.getTime() - lastSent.getTime()) < intervalMs) {
        results.push({ orderId, email, status: 'za_wczesnie' });
        continue;
      }

      // Sprawdź czy klient ma jakiekolwiek statystyki
      const statsExist = await hasAnyStats(orderId);
      if (!statsExist) {
        results.push({ orderId, email, status: 'brak_statystyk' });
        continue;
      }

      try {
        // Pobierz statystyki
        const [summary, dailyStats, weekComparison] = await Promise.all([
          getSummaryStats(orderId, 30),
          getLast30DaysStats(orderId),
          getWeekComparison(orderId),
        ]);

        if (!summary) {
          results.push({ orderId, email, status: 'brak_danych' });
          continue;
        }

        const companyName = order.brief?.companyName || order.billingCompanyName || email.split('@')[0];
        const orderNumber = order.orderNumber || `NX-${orderId}`;

        const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        const reportPeriod = `${thirtyDaysAgo.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })} – ${now.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' })}`;

        // Generuj PDF
        const pdfBuffer = await generateReportPdf({
          companyName,
          orderNumber,
          dailyLimit: order.dailyLimit || 20,
          monthlyAmount: order.monthlyAmount || 1999,
          summary,
          dailyStats,
          weekComparison,
          reportPeriod,
        });

        // Wyślij email
        const sent = await dispatchReportEmail({
          toEmail: email,
          companyName,
          orderNumber,
          summary,
          weekComparison,
          reportPeriod,
          pdfBuffer,
        });

        if (sent) {
          // Update lastReportSentAt
          await fetch(`${payloadUrl}/api/orders/${orderId}`, {
            method: 'PATCH',
            headers: authHeaders,
            body: JSON.stringify({ lastReportSentAt: now.toISOString() }),
          });
          results.push({ orderId, email, status: 'wysłany' });
        } else {
          results.push({ orderId, email, status: 'błąd_wysyłki' });
        }
      } catch (err) {
        console.error(`[Cron/Reports] Błąd dla orderId ${orderId}:`, err);
        results.push({ orderId, email, status: 'błąd' });
      }
    }

    const sent = results.filter(r => r.status === 'wysłany').length;
    const skipped = results.filter(r => r.status === 'za_wczesnie').length;
    const noStats = results.filter(r => r.status === 'brak_statystyk').length;
    const errors = results.filter(r => r.status.startsWith('błąd')).length;

    console.log(`[Cron/Reports] Wynik: ${sent} wysłanych, ${skipped} za wcześnie, ${noStats} bez statystyk, ${errors} błędów.`);

    return new Response(JSON.stringify({
      success: true,
      totalOrders: orders.length,
      sent,
      skipped,
      noStats,
      errors,
      details: results,
    }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });
  } catch (err: any) {
    console.error('[Cron/Reports] Krytyczny błąd:', err);
    return new Response(JSON.stringify({ error: 'Wewnętrzny błąd serwera.' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
}

// Obsługujemy zarówno GET (cron-job.org) jak i POST
export const GET: APIRoute = async ({ request }) => handleDispatch(request);
export const POST: APIRoute = async ({ request }) => handleDispatch(request);
