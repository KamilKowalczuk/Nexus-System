import type { APIRoute } from 'astro';
import { Resend } from 'resend';
import crypto from 'crypto';

export const prerender = false;

// ─── Rate limiter (in-memory, per IP) ───────────────────────────────────────
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT_MAX = 3;
const RATE_LIMIT_WINDOW_MS = 10 * 60 * 1000; // 10 minut

function checkRateLimit(ip: string): { allowed: boolean; resetInMs: number } {
  const now = Date.now();
  const entry = rateLimitMap.get(ip);

  if (!entry || now > entry.resetAt) {
    rateLimitMap.set(ip, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return { allowed: true, resetInMs: 0 };
  }

  if (entry.count >= RATE_LIMIT_MAX) {
    return { allowed: false, resetInMs: entry.resetAt - now };
  }

  entry.count++;
  return { allowed: true, resetInMs: 0 };
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function json(body: object, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

export const POST: APIRoute = async ({ request }) => {
  // ─── Rate limiting ───
  const ip =
    request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
    request.headers.get('cf-connecting-ip') ||
    '127.0.0.1';

  const { allowed, resetInMs } = checkRateLimit(ip);
  if (!allowed) {
    const minutes = Math.ceil(resetInMs / 60000);
    return json({ error: 'rate_limit', resetInMinutes: minutes }, 429);
  }

  // ─── Parsuj body ───
  let body: { email?: string; orderNumber?: string };
  try {
    body = await request.json();
  } catch {
    return json({ error: 'Nieprawidłowe dane' }, 400);
  }

  const { email, orderNumber } = body;

  if (!email || !orderNumber) {
    return json({ error: 'Wymagane pola: email i numer zamówienia' }, 400);
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const resendKey = import.meta.env.RESEND_API_KEY;
  const siteUrl = import.meta.env.SITE_URL || 'https://nexusagent.pl';
  const apiKey = import.meta.env.PAYLOAD_API_KEY;

  const authHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) authHeaders['Authorization'] = `users API-Key ${apiKey}`;

  try {
    // ─── Znajdź zamówienie wg email + orderNumber ───
    const searchRes = await fetch(
      `${payloadUrl}/api/orders?where[customerEmail][equals]=${encodeURIComponent(email)}&where[orderNumber][equals]=${encodeURIComponent(orderNumber)}&limit=1&depth=0`,
      { headers: authHeaders }
    );

    // Zawsze odpowiadaj tą samą wiadomością dla bezpieczeństwa
    const SAFE_RESPONSE = { ok: true, message: 'Jeśli dane są poprawne, link zostanie wysłany na Twój adres email.' };

    if (!searchRes.ok) {
      return json(SAFE_RESPONSE, 200);
    }

    const searchData = await searchRes.json();
    const order = searchData.docs?.[0];

    if (!order) {
      // Zamówienie nie istnieje — informujemy użytkownika
      return json({ ok: false, state: 'not_found' }, 200);
    }

    const resend = resendKey ? new Resend(resendKey) : null;
    const orderId = order.id;

    if (order.brief) {
      // ─── Stan 1: Brief wypełniony → wysyłamy link do edycji ───
      const editToken = crypto.randomBytes(32).toString('hex');

      await fetch(`${payloadUrl}/api/orders/${orderId}`, {
        method: 'PATCH',
        headers: authHeaders,
        body: JSON.stringify({ editToken }),
      });

      if (resend && order.customerEmail) {
        const link = `${siteUrl}/onboarding/${editToken}?mode=edit`;
        await resend.emails.send({
          from: 'NEXUS Agent <onboarding@nexusagent.pl>',
          to: order.customerEmail,
          subject: 'NEXUS Agent – link do edycji Twojego briefu',
          html: buildEditEmail(link),
        });
      }
    } else {
      // ─── Stan 2: Brak briefu → wysyłamy link onboardingowy ───
      const onboardingToken = crypto.randomBytes(32).toString('hex');

      await fetch(`${payloadUrl}/api/orders/${orderId}`, {
        method: 'PATCH',
        headers: authHeaders,
        body: JSON.stringify({ onboardingToken }),
      });

      if (resend && order.customerEmail) {
        const link = `${siteUrl}/onboarding/${onboardingToken}`;
        await resend.emails.send({
          from: 'NEXUS Agent <onboarding@nexusagent.pl>',
          to: order.customerEmail,
          subject: 'NEXUS Agent – ponowny link do konfiguracji systemu',
          html: buildOnboardingResendEmail(link),
        });
      }
    }

    return json(SAFE_RESPONSE, 200);
  } catch (err: any) {
    console.error('[resend-from-website] Error:', err?.message);
    return json({ error: 'Błąd serwera. Spróbuj ponownie.' }, 500);
  }
};

// ─── Template: edycja briefu ─────────────────────────────────────────────────
function buildEditEmail(link: string): string {
  return `<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        <tr>
          <td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
            <img src="https://nexusagent.pl/logo.webp" alt="NEXUS Agent" width="80" height="80" style="display:block;margin:0 auto 12px auto;"/>
            <div style="font-family:monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;">NEXUS REVENUE PROTOCOL</div>
          </td>
        </tr>
        <tr>
          <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">
            <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#0ceaed;margin-bottom:16px;">Link do edycji briefu</div>
            <h1 style="margin:0 0 16px;font-size:22px;font-weight:800;text-transform:uppercase;color:#fff;">Edytuj swój Brief Wdrożeniowy</h1>
            <p style="margin:0 0 20px;color:#94a3b8;font-size:14px;line-height:1.6;">
              Na Twoją prośbę wygenerowaliśmy <strong style="color:#fff;">nowy jednorazowy link</strong> do edycji Twojego briefu.
              Możesz zmienić dane firmy, kampanii lub ustawień AI.
            </p>
            <div style="text-align:center;margin:28px 0;">
              <a href="${link}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;font-weight:800;font-size:14px;text-transform:uppercase;letter-spacing:0.1em;padding:16px 40px;border-radius:100px;text-decoration:none;box-shadow:0 0 30px rgba(168,85,247,0.4);">✏️ Edytuj Brief</a>
            </div>
            <div style="font-size:12px;color:#64748b;background:rgba(168,85,247,0.05);border:1px solid rgba(168,85,247,0.2);border-radius:12px;padding:16px;">
              <strong style="color:#a855f7;">Bezpieczeństwo:</strong> Link jest jednorazowy i chroniony. Jeśli nie prosiłeś o edycję – zignoruj tę wiadomość.
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 40px;text-align:center;">
            <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#334155;">NEXUS AGENT · nexusagent.pl · kontakt@nexusagent.pl</div>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>`;
}

// ─── Template: ponowny link onboardingu ──────────────────────────────────────
function buildOnboardingResendEmail(link: string): string {
  return `<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        <tr>
          <td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
            <img src="https://nexusagent.pl/logo.webp" alt="NEXUS Agent" width="80" height="80" style="display:block;margin:0 auto 12px auto;"/>
            <div style="font-family:monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;">NEXUS REVENUE PROTOCOL</div>
          </td>
        </tr>
        <tr>
          <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">
            <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#0ceaed;margin-bottom:16px;">Ponowny link do konfiguracji</div>
            <h1 style="margin:0 0 16px;font-size:22px;font-weight:800;text-transform:uppercase;color:#fff;">Wysyłamy Ci nowy link do briefu</h1>
            <p style="margin:0 0 20px;color:#94a3b8;font-size:14px;line-height:1.6;">
              Na Twoją prośbę generujemy <strong style="color:#fff;">nowy jednorazowy link</strong> do wypełnienia Briefu Wdrożeniowego.
              <strong style="color:#e2e8f0;">Poprzedni link przestał działać</strong> – używaj wyłącznie tego poniżej.
            </p>
            <div style="text-align:center;margin:28px 0;">
              <a href="${link}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;font-weight:800;font-size:14px;text-transform:uppercase;letter-spacing:0.1em;padding:16px 40px;border-radius:100px;text-decoration:none;box-shadow:0 0 30px rgba(168,85,247,0.4);">⚡ Otwórz Brief Wdrożeniowy</a>
            </div>
            <div style="font-size:12px;color:#64748b;background:rgba(168,85,247,0.05);border:1px solid rgba(168,85,247,0.2);border-radius:12px;padding:16px;">
              <strong style="color:#a855f7;">Bezpieczeństwo:</strong> Link jest jednorazowy. Po wypełnieniu formularza zostanie automatycznie unieważniony.
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 40px;text-align:center;">
            <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#334155;">NEXUS AGENT · nexusagent.pl · kontakt@nexusagent.pl</div>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>`;
}
