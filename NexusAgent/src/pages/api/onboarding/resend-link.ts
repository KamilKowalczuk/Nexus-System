import type { APIRoute } from 'astro';
import { Resend } from 'resend';
import crypto from 'crypto';

export const prerender = false;

const SITE_URL = import.meta.env.SITE_URL || 'https://nexusagent.pl';

// BEZPIECZEŃSTWO: Ograniczamy CORS do własnej domeny produkcyjnej.
// Wildcard '*' pozwalałby złośliwym stronom wywoływać ten endpoint z przeglądarki ofiary.
const SITE_ORIGIN = import.meta.env.SITE_URL || 'https://nexusagent.pl';

function getCorsHeaders(request: Request) {
  const origin = request.headers.get('Origin');
  const siteUrl = import.meta.env.SITE_URL || 'https://nexusagent.pl';
  const payloadUrl = import.meta.env.PAYLOAD_URL; // Adres backendu (np. Railway)

  // Lista dozwolonych originów
  const allowedOrigins = [siteUrl];
  if (payloadUrl) {
    // Dodajemy czysty origin z PAYLOAD_URL (usuwamy ścieżki jeśli są)
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

function jsonResponse(body: object, status: number, request: Request, headers?: Record<string, string>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...getCorsHeaders(request), ...headers },
  });
}

function emailHeader(): string {
  return `
    <tr>
      <td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
        <img src="https://nexusagent.pl/logo.webp" alt="NEXUS Agent" width="120" height="120" style="display:block;margin:0 auto 12px auto;" />
        <div style="font-family:monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;margin-bottom:8px;">NEXUS REVENUE PROTOCOL</div>
        <div style="font-size:28px;font-weight:900;text-transform:uppercase;letter-spacing:-0.02em;color:#fff;">NEXUS Agent</div>
      </td>
    </tr>
  `;
}

function emailFooter(): string {
  return `
    <tr>
      <td style="padding:24px 40px;text-align:center;">
        <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#334155;">NEXUS AGENT · nexusagent.pl · Wsparcie: kontakt@nexusagent.pl</div>
      </td>
    </tr>
  `;
}

function buildResendOnboardingEmail(link: string): string {
  return `
<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /></head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        ${emailHeader()}
        <tr>
          <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">
            <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#0ceaed;margin-bottom:16px;">Ponowny link do konfiguracji</div>
            <h1 style="margin:0 0 16px;font-size:22px;font-weight:800;text-transform:uppercase;letter-spacing:-0.02em;color:#fff;line-height:1.2;">Wysyłamy nowy link do briefu</h1>
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
        ${emailFooter()}
      </table>
    </td></tr>
  </table>
</body>
</html>
  `;
}

function buildResendEditEmail(link: string): string {
  return `
<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /></head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        ${emailHeader()}
        <tr>
          <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">
            <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#0ceaed;margin-bottom:16px;">Link do edycji briefu</div>
            <h1 style="margin:0 0 16px;font-size:22px;font-weight:800;text-transform:uppercase;letter-spacing:-0.02em;color:#fff;line-height:1.2;">Wysyłamy link do edycji formularza</h1>
            <p style="margin:0 0 20px;color:#94a3b8;font-size:14px;line-height:1.6;">
              Na Twoją prośbę generujemy <strong style="color:#fff;">bezpieczny link do edycji</strong> wcześniej wypełnionego Briefu Wdrożeniowego.
              Możesz zmienić dane firmy, kampanii lub ustawień – każda zmiana zostanie zapisana i uwzględniona przy pracy agenta.
            </p>
            <div style="text-align:center;margin:28px 0;">
              <a href="${link}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;font-weight:800;font-size:14px;text-transform:uppercase;letter-spacing:0.1em;padding:16px 40px;border-radius:100px;text-decoration:none;box-shadow:0 0 30px rgba(168,85,247,0.4);">✏️ Edytuj Brief</a>
            </div>
            <div style="font-size:12px;color:#64748b;background:rgba(168,85,247,0.05);border:1px solid rgba(168,85,247,0.2);border-radius:12px;padding:16px;">
              <strong style="color:#a855f7;">Bezpieczeństwo:</strong> Link jest chroniony. Jeśli nie prosiłeś o edycję – zignoruj tę wiadomość.
            </div>
          </td>
        </tr>
        ${emailFooter()}
      </table>
    </td></tr>
  </table>
</body>
</html>
  `;
}

export const OPTIONS: APIRoute = ({ request }) => {
  return new Response(null, { status: 204, headers: getCorsHeaders(request) });
};

const rateLimitMap = new Map<string, number[]>();

export const POST: APIRoute = async ({ request, clientAddress }) => {
  const ip = clientAddress || '127.0.0.1';

  // Ochrona przed spamowaniem re-sendów (max 3 próby z 1 IP na godzinę)
  const now = Date.now();
  const times = rateLimitMap.get(ip) || [];
  const recentTimes = times.filter(t => now - t < 3600000); // 1h
  if (recentTimes.length >= 3) {
    return jsonResponse({ error: 'Za dużo prób. Spróbuj powonnie za godzinę.' }, 429, request);
  }
  recentTimes.push(now);
  if (rateLimitMap.size > 1000) rateLimitMap.clear();
  rateLimitMap.set(ip, recentTimes);

  let body: { orderId?: string; type?: 'onboarding' | 'edit' };
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: 'Nieprawidłowy JSON' }, 400, request);
  }
  const { orderId, type } = body;

  if (!orderId) {
    return jsonResponse({ error: 'Brak orderId' }, 400, request);
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const resendKey = import.meta.env.RESEND_API_KEY;
  const apiKey = import.meta.env.PAYLOAD_API_KEY;

  const authHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(apiKey ? { 'Authorization': `users API-Key ${apiKey}` } : {})
  };

  try {
    const orderRes = await fetch(`${payloadUrl}/api/orders/${orderId}?depth=2`, {
      headers: authHeaders,
    });

    if (!orderRes.ok) {
      return jsonResponse({ error: 'Nie znaleziono zamówienia' }, 404, request);
    }

    const order = await orderRes.json();

    if (!order.customerEmail) {
      return jsonResponse({ error: 'Brak emaila klienta w zamówieniu' }, 400, request);
    }

    const resend = resendKey ? new Resend(resendKey) : null;
    const mode = type || 'onboarding';

      if (mode === 'onboarding') {
      if (order.brief) {
        return jsonResponse({ error: 'Brief już wypełniony – użyj trybu edycji.' }, 409, request);
      }

      const token = crypto.randomBytes(32).toString('hex');
      // Token ważny 30 dni
      const onboardingTokenExpiry = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();

      await fetch(`${payloadUrl}/api/orders/${orderId}`, {
        method: 'PATCH',
        headers: authHeaders,
        body: JSON.stringify({ onboardingToken: token, onboardingTokenExpiry }),
      });

      if (resend) {
        const link = `${SITE_URL}/onboarding/${token}`;
        await resend.emails.send({
          from: 'NEXUS Agent <onboarding@nexusagent.pl>',
          to: order.customerEmail,
          subject: 'NEXUS Agent – nowy link do konfiguracji (poprzedni nieaktualny)',
          html: buildResendOnboardingEmail(link),
        });
      }

      return jsonResponse({ ok: true, mode: 'onboarding' }, 200, request);
    }

    if (!order.brief) {
      return jsonResponse({ error: 'Brak briefu do edycji.' }, 409, request);
    }

    const editToken = crypto.randomBytes(32).toString('hex');
    // Token ważny 7 dni
    const editTokenExpiry = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

    await fetch(`${payloadUrl}/api/orders/${orderId}`, {
      method: 'PATCH',
      headers: authHeaders,
      body: JSON.stringify({ editToken, editTokenExpiry }),
    });

      if (resend) {
      const link = `${SITE_URL}/onboarding/${editToken}?mode=edit`;
      await resend.emails.send({
        from: 'NEXUS Agent <onboarding@nexusagent.pl>',
        to: order.customerEmail,
        subject: 'NEXUS Agent – link do edycji briefu wdrożeniowego',
        html: buildResendEditEmail(link),
      });
    }

    return jsonResponse({ ok: true, mode: 'edit' }, 200, request);
  } catch (err) {
    console.error('[onboarding/resend-link] Error:', err);
    return jsonResponse({ error: 'Błąd serwera' }, 500, request);
  }
};
