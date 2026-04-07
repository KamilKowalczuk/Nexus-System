import type { APIRoute } from 'astro';
import crypto from 'node:crypto';

export const prerender = false;

// Blokada per IP (5 prób / 15 minut)
const failedAttemptsMap = new Map<string, number>();

// Blokada per orderId — niezależna od IP rotation.
// Po 5 błędnych próbach OTP dla danego zamówienia kasujemy kod z bazy,
// co wymusza ponowne wysłanie (rate-limited przez send-otp).
const failedByOrderMap = new Map<string, number>();

export const POST: APIRoute = async ({ request, clientAddress }) => {
  const ip = clientAddress || '127.0.0.1';

  const failedCount = failedAttemptsMap.get(ip) || 0;
  if (failedCount >= 5) {
    return new Response(JSON.stringify({ error: 'Zbyt dużo błędnych prób z tego adresu IP. Odczekaj 15 minut i spróbuj wygenerować nowy kod.' }), {
      status: 429, headers: { 'Content-Type': 'application/json' },
    });
  }

  const body = await request.json();
  const token = body.token as string | undefined;
  const otp = body.otp as string | undefined;

  if (!token || !otp) {
    return new Response(JSON.stringify({ error: 'Brak tokenu lub kodu OTP' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';

  // Autoryzacja z API Key
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  const authHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiKey) {
    authHeaders['Authorization'] = `users API-Key ${apiKey}`;
  }

  let finalMode: 'onboarding' | 'edit' = 'onboarding';
  let order: any = null;

  try {
    // ─── AUTO-DETEKCJA trybu po tokenie ───────────────────────────────────
    // Najpierw szukamy w onboardingToken
    const searchResOnboarding = await fetch(
      `${payloadUrl}/api/orders?where[onboardingToken][equals]=${encodeURIComponent(String(token))}&limit=1&depth=0`,
      { headers: authHeaders }
    );
    if (searchResOnboarding.ok) {
      const dataOnboarding = await searchResOnboarding.json();
      if (dataOnboarding.docs?.length > 0) {
        finalMode = 'onboarding';
        order = dataOnboarding.docs[0];
      }
    }

    // Jeśli nie znaleziono w onboardingToken, szukamy w editToken
    // UWAGA: depth=2 — Payload zagnieżdźi obiekt Brief inline w order.brief
    if (!order) {
      const searchResEdit = await fetch(
        `${payloadUrl}/api/orders?where[editToken][equals]=${encodeURIComponent(String(token))}&limit=1&depth=2`,
        { headers: authHeaders }
      );
      if (searchResEdit.ok) {
        const dataEdit = await searchResEdit.json();
        if (dataEdit.docs?.length > 0) {
          finalMode = 'edit';
          order = dataEdit.docs[0];
        }
      }
    }

    if (!order) {
      return new Response(JSON.stringify({ error: 'Nieprawidłowy token' }), {
        status: 404, headers: { 'Content-Type': 'application/json' },
      });
    }

    // Sprawdź blokadę per-orderId (niezależną od IP)
    const orderFailCount = failedByOrderMap.get(String(order.id)) || 0;
    if (orderFailCount >= 5) {
      return new Response(JSON.stringify({ error: 'Zbyt dużo błędnych prób dla tego zamówienia. Wygeneruj nowy kod.' }), {
        status: 429, headers: { 'Content-Type': 'application/json' },
      });
    }


    // W trybie edit brief musi istnieć; w trybie onboarding brief nie może istnieć (burn after reading)
    if (finalMode === 'edit' && !order.brief) {
      return new Response(JSON.stringify({ error: 'Brak briefu do edycji.' }), {
        status: 409, headers: { 'Content-Type': 'application/json' },
      });
    }
    if (finalMode !== 'edit' && order.brief) {
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

    // Walidacja kodu OTP - OCHRONA PRZED TIMING ATTACKS
    const expectedOtp = String(order.otpCode || '').trim();
    const providedOtp = String(otp || '').trim();

    const expectedBuffer = Buffer.from(expectedOtp);
    const providedBuffer = Buffer.from(providedOtp);

    let otpMatches = false;
    if (expectedBuffer.length === providedBuffer.length && expectedBuffer.length > 0) {
      otpMatches = crypto.timingSafeEqual(expectedBuffer, providedBuffer);
    }

    if (!otpMatches) {
      // Inkrementuj licznik per-IP
      failedAttemptsMap.set(ip, failedCount + 1);
      setTimeout(() => failedAttemptsMap.delete(ip), 15 * 60 * 1000);

      // Inkrementuj licznik per-orderId
      const newOrderFailCount = orderFailCount + 1;
      if (newOrderFailCount >= 5) {
        // Unieważnij OTP w bazie — zmusza do ponownego wysłania (rate-limited)
        failedByOrderMap.delete(String(order.id));
        await fetch(`${payloadUrl}/api/orders/${order.id}`, {
          method: 'PATCH',
          headers: authHeaders,
          body: JSON.stringify({ otpCode: null, otpExpiry: null }),
        }).catch(() => {});
        return new Response(JSON.stringify({ error: 'Zbyt dużo błędnych prób. Kod został unieważniony — wygeneruj nowy.' }), {
          status: 429, headers: { 'Content-Type': 'application/json' },
        });
      }
      failedByOrderMap.set(String(order.id), newOrderFailCount);

      return new Response(JSON.stringify({ error: 'Nieprawidłowy kod. Sprawdź email i spróbuj ponownie.' }), {
        status: 401, headers: { 'Content-Type': 'application/json' },
      });
    }

    if (!order.otpExpiry || new Date(order.otpExpiry) < new Date()) {
      return new Response(JSON.stringify({ error: 'Kod wygasł. Wygeneruj nowy.' }), {
        status: 401, headers: { 'Content-Type': 'application/json' },
      });
    }

    // OTP prawidłowy – wyczyść liczniki i OTP z bazy
    failedAttemptsMap.delete(ip);
    failedByOrderMap.delete(String(order.id));
    await fetch(`${payloadUrl}/api/orders/${order.id}`, {
      method: 'PATCH',
      headers: authHeaders,
      body: JSON.stringify({ otpCode: null, otpExpiry: null }),
    });

    // ─── Jeżeli edycja, brief jest już zagnieżdżony w order.brief (depth=2) ──
    let briefData: Record<string, unknown> | null = null;
    let briefId: string | number | null = null;

    if (finalMode === 'edit' && order.brief) {
      if (typeof order.brief === 'object' && order.brief !== null) {
        briefId = order.brief.id;
        briefData = order.brief as Record<string, unknown>;
      } else {
        briefId = order.brief;
        
        try {
          const forceAuthHeaders = {
            'Content-Type': 'application/json',
            ...(apiKey ? { 'Authorization': `users API-Key ${apiKey.trim()}` } : {})
          };

          const briefRes = await fetch(`${payloadUrl}/api/briefs/${briefId}?depth=0`, { 
            headers: forceAuthHeaders 
          });

          if (briefRes.ok) {
            const briefJson = await briefRes.json();
            briefData = (briefJson.doc || briefJson) as Record<string, unknown>;
          } else {
            console.error(`[verify-otp] Fallback fetch failed: ${await briefRes.text()}`);
          }
        } catch (e) {
          console.error(`[verify-otp] Błąd podczas fetch briefa:`, e);
        }
      }
    }


    return new Response(JSON.stringify({
      verified: true,
      mode: finalMode,
      orderId: order.id,
      customerEmail: order.customerEmail,
      dailyLimit: order.dailyLimit,
      monthlyAmount: order.monthlyAmount,
      briefId,
      brief: briefData,
    }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    console.error('[verify-otp] Error:', err);
    return new Response(JSON.stringify({ error: 'Błąd serwera' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
};
