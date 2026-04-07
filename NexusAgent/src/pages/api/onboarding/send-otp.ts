import type { APIRoute } from 'astro';
import { Resend } from 'resend';
import crypto from 'node:crypto';

export const prerender = false;

function sanitize(str: any): string {
  if (typeof str !== 'string') return String(str || '');
  return str.replace(/[\x00-\x1F\x7F]/g, ' ').trim();
}

function generateOtp(): string {
  // Kryptograficznie bezpieczny generator liczb losowych
  return crypto.randomInt(100000, 1000000).toString();
}

const rateLimitMap = new Map<string, number[]>();

export const POST: APIRoute = async ({ request, clientAddress }) => {
  const ip = clientAddress || '127.0.0.1';
  
  const now = Date.now();
  const times = rateLimitMap.get(ip) || [];
  const recentTimes = times.filter(t => now - t < 120000); // 2 minuty
  if (recentTimes.length >= 2) {
    return new Response(JSON.stringify({ error: 'Za dużo prób wysyłania kodów. Odczekaj chwilę.' }), {
      status: 429, headers: { 'Content-Type': 'application/json' },
    });
  }
  recentTimes.push(now);
  if (rateLimitMap.size > 1000) rateLimitMap.clear();
  rateLimitMap.set(ip, recentTimes);

  const body = await request.json();
  const { token, email } = body as { token?: string; email?: string };

  if (!token || !email) {
    return new Response(JSON.stringify({ error: 'Brak tokenu lub emaila' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';

  // Autoryzacja z API Key (wymagana dla Orders z !!user na read)
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  const authHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiKey) {
    authHeaders['Authorization'] = `users API-Key ${apiKey}`;
  }

  try {
    // ─── AUTO-DETEKCJA trybu po tokenie (nie polegamy na mode z frontu) ───
    let order: any = null;
    let detectedMode: 'onboarding' | 'edit' = 'onboarding';

    // Najpierw szukamy w onboardingToken
    const resOnboarding = await fetch(
      `${payloadUrl}/api/orders?where[onboardingToken][equals]=${encodeURIComponent(String(token))}&limit=1&depth=0`,
      { headers: authHeaders }
    );
    if (resOnboarding.ok) {
      const dataOnboarding = await resOnboarding.json();
      if (dataOnboarding.docs?.length > 0) {
        order = dataOnboarding.docs[0];
        detectedMode = 'onboarding';
      }
    }

    // Jeśli nie znaleziono w onboardingToken, szukamy w editToken
    if (!order) {
      const resEdit = await fetch(
        `${payloadUrl}/api/orders?where[editToken][equals]=${encodeURIComponent(String(token))}&limit=1&depth=0`,
        { headers: authHeaders }
      );
      if (resEdit.ok) {
        const dataEdit = await resEdit.json();
        if (dataEdit.docs?.length > 0) {
          order = dataEdit.docs[0];
          detectedMode = 'edit';
        }
      }
    }

    // BEZPIECZEŃSTWO: User Enumeration fix.
    const genericTokenError = 'Nieprawidłowy link onboardingowy lub adres email.';

    if (!order) {
      return new Response(JSON.stringify({ error: genericTokenError }), {
        status: 401, headers: { 'Content-Type': 'application/json' },
      });
    }

    // W trybie edit brief musi istnieć; w trybie onboarding brief nie może istnieć (burn after reading)
    if (detectedMode === 'edit' && !order.brief) {
      return new Response(JSON.stringify({ error: 'Brak briefu do edycji.' }), {
        status: 409, headers: { 'Content-Type': 'application/json' },
      });
    }
    if (detectedMode !== 'edit' && order.brief) {
      return new Response(JSON.stringify({ error: 'Ten link został już wykorzystany. Brief jest zapisany.' }), {
        status: 410, headers: { 'Content-Type': 'application/json' },
      });
    }

    // Czyścimy przestarzałe OTP (>24h) jeśli istnieje
    if (order.otpExpiry) {
      const otpTime = new Date(order.otpExpiry).getTime();
      const cutoff = Date.now() - 24 * 60 * 60 * 1000;
      if (otpTime < cutoff) {
        await fetch(`${payloadUrl}/api/orders/${order.id}`, {
          method: 'PATCH',
          headers: authHeaders,
          body: JSON.stringify({ otpCode: null, otpExpiry: null }),
        });
        order.otpCode = null;
        order.otpExpiry = null;
      }
    }

    // Email musi być taki sam jak w zamówieniu
    if (order.customerEmail.toLowerCase() !== email.toLowerCase()) {
      return new Response(JSON.stringify({ error: genericTokenError }), {
        status: 401, headers: { 'Content-Type': 'application/json' },
      });
    }

    const otp = generateOtp();
    const expiry = new Date(Date.now() + 10 * 60 * 1000).toISOString(); // 10 minut

    // Zapisz OTP do Order (z auth headers!)
    const patchRes = await fetch(`${payloadUrl}/api/orders/${order.id}`, {
      method: 'PATCH',
      headers: authHeaders,
      body: JSON.stringify({ otpCode: otp, otpExpiry: expiry }),
    });

    if (!patchRes.ok) {
      console.error('[send-otp] Błąd zapisu OTP, PATCH status:', patchRes.status, sanitize(await patchRes.text()));
      return new Response(JSON.stringify({ error: 'Błąd zapisu OTP' }), {
        status: 500, headers: { 'Content-Type': 'application/json' },
      });
    }

    // Wyślij OTP przez Resend
    const resendKey = import.meta.env.RESEND_API_KEY;
    if (resendKey) {
      const resend = new Resend(resendKey);
      await resend.emails.send({
        from: 'NEXUS Agent <onboarding@nexusagent.pl>',
        to: email,
        subject: `${otp} – Twój kod weryfikacyjny NEXUS`,
        html: `
          <div style="background:#050508;padding:40px;font-family:monospace;color:#e2e8f0;border-radius:16px;">
            <div style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;margin-bottom:16px;">NEXUS AGENT – WERYFIKACJA 2FA</div>
            <div style="font-size:14px;color:#94a3b8;margin-bottom:24px;">Twój jednorazowy kod weryfikacyjny:</div>
            <div style="font-size:48px;font-weight:900;letter-spacing:0.15em;color:#a855f7;text-align:center;padding:24px;background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.3);border-radius:12px;margin-bottom:24px;">${otp}</div>
            <div style="font-size:12px;color:#64748b;">Kod jest ważny przez <strong style="color:#e2e8f0;">10 minut</strong>. Nie udostępniaj go nikomu.</div>
          </div>
        `,
      });
    }

    return new Response(JSON.stringify({ sent: true, mode: detectedMode }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    console.error('[send-otp] Error:', err);
    return new Response(JSON.stringify({ error: 'Błąd serwera' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
};
