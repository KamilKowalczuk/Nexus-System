/**
 * /api/reports/send.ts
 * ────────────────────────────────────────────────────────────────────
 * Natychmiastowa wysyłka raportu statystyk kampanii dla konkretnego
 * zamówienia. Wywoływany przez przycisk w panelu Payload CMS.
 *
 * POST { orderId: number }
 * Auth: API Key (REPORT_SECRET lub PAYLOAD_API_KEY)
 * ────────────────────────────────────────────────────────────────────
 */

import type { APIRoute } from 'astro';
import { getSummaryStats, getLast30DaysStats, getWeekComparison, hasAnyStats } from '../../../utils/campaignStats';
import { generateReportPdf } from '../../../utils/reportPdf';
import { dispatchReportEmail } from '../../../utils/reportEmail';

export const prerender = false;

function getCorsHeaders(request: Request) {
  const origin = request.headers.get('Origin');
  const siteUrl = import.meta.env.SITE_URL || 'https://nexusagent.pl';
  const payloadUrl = import.meta.env.PAYLOAD_URL;

  // Lista dozwolonych originów
  const allowedOrigins = [siteUrl];
  if (payloadUrl) {
    try {
      const pUrl = new URL(payloadUrl);
      allowedOrigins.push(pUrl.origin);
    } catch { /* ignore */ }
  }

  // Jeśli żądanie pochodzi z dozwolonego źródła, odbijamy je w nagłówku
  const allowedOrigin = (origin && allowedOrigins.includes(origin)) ? origin : siteUrl;

  return {
    'Access-Control-Allow-Origin': allowedOrigin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function jsonResponse(body: object, status: number, request: Request) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...getCorsHeaders(request) },
  });
}

export const OPTIONS: APIRoute = ({ request }) => {
  return new Response(null, { status: 204, headers: getCorsHeaders(request) });
};

export const POST: APIRoute = async ({ request }) => {
  try {
    let body;
    try {
      body = await request.json();
    } catch {
      return jsonResponse({ error: 'Nieprawidłowy JSON' }, 400, request);
    }

    const { orderId } = body;

    if (!orderId) {
      return jsonResponse({ error: 'Brak orderId' }, 400, request);
    }

    const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
    const apiKey = import.meta.env.PAYLOAD_API_KEY;
    const authHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) authHeaders['Authorization'] = `users API-Key ${apiKey}`;

    // 1. Pobierz zamówienie z Payload
    const orderRes = await fetch(`${payloadUrl}/api/orders/${orderId}?depth=1`, { headers: authHeaders });
    if (!orderRes.ok) {
      return jsonResponse({ error: 'Zamówienie nie znalezione' }, 404, request);
    }

    const order = await orderRes.json();

    if (!order.customerEmail) {
      return jsonResponse({ error: 'Brak emaila klienta w zamówieniu' }, 400, request);
    }

    // 2. Sprawdź czy klient ma dane statystyczne
    const statsExist = await hasAnyStats(orderId);
    if (!statsExist) {
      return jsonResponse({ error: 'Brak danych statystycznych dla tego klienta w bazie bota.' }, 404, request);
    }

    // 3. Pobierz statystyki
    const [summary, dailyStats, weekComparison] = await Promise.all([
      getSummaryStats(orderId, 30),
      getLast30DaysStats(orderId),
      getWeekComparison(orderId),
    ]);

    if (!summary) {
      return jsonResponse({ error: 'Brak zagregowanych danych statystycznych.' }, 404, request);
    }

    // 4. Przygotuj dane raportu
    const companyName = order.brief?.companyName || order.billingCompanyName || order.customerEmail.split('@')[0];
    const orderNumber = order.orderNumber || `NX-${orderId}`;

    const now = new Date();
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    const reportPeriod = `${thirtyDaysAgo.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })} – ${now.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' })}`;

    // 5. Generuj PDF
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

    // 6. Wyślij email z PDF
    const emailSent = await dispatchReportEmail({
      toEmail: order.customerEmail,
      companyName,
      orderNumber,
      summary,
      weekComparison,
      reportPeriod,
      pdfBuffer,
    });

    if (!emailSent) {
      return jsonResponse({ error: 'Błąd wysyłki emaila przez Resend.' }, 500, request);
    }

    // 7. Zaktualizuj lastReportSentAt w Orders
    await fetch(`${payloadUrl}/api/orders/${orderId}`, {
      method: 'PATCH',
      headers: authHeaders,
      body: JSON.stringify({ lastReportSentAt: new Date().toISOString() }),
    });

    return jsonResponse({
      success: true,
      message: `Raport wysłany do ${order.customerEmail}`,
      email: order.customerEmail,
    }, 200, request);

  } catch (err: any) {
    console.error('[API/reports/send] CRITICAL ERROR:', err);
    return jsonResponse({ 
      error: `Błąd serwera: ${err.message || 'Nieznany'}`,
      stack: err.stack?.split('\n').slice(0, 3).join(' | ')
    }, 500, request);
  }
};
