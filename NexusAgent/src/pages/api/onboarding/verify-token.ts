import type { APIRoute } from 'astro';

export const prerender = false;

export const GET: APIRoute = async ({ url }) => {
  const token = url.searchParams.get('token');

  if (!token) {
    return new Response(JSON.stringify({ valid: false, error: 'Brak tokenu' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ valid: false, error: 'Konfiguracja serwera: brak PAYLOAD_API_KEY.' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
  const authHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    'Authorization': `users API-Key ${apiKey}`,
  };

  try {
    // ─── SPRAWDZAMY CZY TO JEST LINK "ONBOARDING" ──────────────────────────────────
    const res = await fetch(
      `${payloadUrl}/api/orders?where[onboardingToken][equals]=${encodeURIComponent(String(token))}&limit=1&depth=0`,
      { headers: authHeaders }
    );

    if (res.ok) {
      const data = await res.json();
      if (data.docs?.length > 0) {
        const order = data.docs[0];

        // Sprawdź czy brief już wypełniony (burn after reading)
        if (order.brief) {
          return new Response(JSON.stringify({ valid: false, error: 'Ten link został już wykorzystany. Brief wdrożeniowy jest w trakcie realizacji.' }), {
            status: 410, headers: { 'Content-Type': 'application/json' },
          });
        }

        // Sprawdź wygaśnięcie tokenu onboardingowego (30 dni)
        if (order.onboardingTokenExpiry && new Date(order.onboardingTokenExpiry) < new Date()) {
          return new Response(JSON.stringify({ valid: false, error: 'Link onboardingowy wygasł. Skontaktuj się z NEXUS aby otrzymać nowy link.' }), {
            status: 410, headers: { 'Content-Type': 'application/json' },
          });
        }

        return new Response(JSON.stringify({
          valid: true,
          mode: 'onboarding',
          orderId: order.id,
          customerEmail: order.customerEmail,
          dailyLimit: order.dailyLimit,
          monthlyAmount: order.monthlyAmount,
        }), {
          status: 200, headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    // TRYB 2: Edycja istniejącego briefu – używamy globalnego authHeaders

    const editRes = await fetch(
      `${payloadUrl}/api/orders?where[editToken][equals]=${encodeURIComponent(String(token))}&limit=1&depth=0`,
      { headers: authHeaders }
    );

    if (!editRes.ok) {
      return new Response(JSON.stringify({ valid: false, error: 'Błąd bazy danych' }), {
        status: 500, headers: { 'Content-Type': 'application/json' },
      });
    }

    const editData = await editRes.json();
    if (!editData.docs?.length) {
      return new Response(JSON.stringify({ valid: false, error: 'Nieprawidłowy lub wygasły link edycji' }), {
        status: 404, headers: { 'Content-Type': 'application/json' },
      });
    }

    const order = editData.docs[0];

    // Sprawdź wygaśnięcie tokenu edycji (7 dni)
    if (order.editTokenExpiry && new Date(order.editTokenExpiry) < new Date()) {
      return new Response(JSON.stringify({ valid: false, error: 'Link edycji wygasł. Poproś o wysłanie nowego linku z Panelu.' }), {
        status: 410, headers: { 'Content-Type': 'application/json' },
      });
    }

    const rawBrief = order.brief;
    const briefId = typeof rawBrief === 'object' ? rawBrief?.id : rawBrief;

    if (!briefId) {
      return new Response(JSON.stringify({ valid: false, error: 'Ten link nie ma jeszcze podpiętego briefu do edycji.' }), {
        status: 409, headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      valid: true,
      mode: 'edit',
      orderId: order.id,
      customerEmail: order.customerEmail,
      dailyLimit: order.dailyLimit,
      monthlyAmount: order.monthlyAmount,
      briefId,
    }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    console.error('[verify-token] Error:', err);
    return new Response(JSON.stringify({ valid: false, error: 'Błąd serwera' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
};
