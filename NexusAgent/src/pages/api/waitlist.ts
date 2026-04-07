import type { APIRoute } from 'astro';

export const prerender = false;

const rateLimitMap = new Map<string, number>();

export const POST: APIRoute = async ({ request }) => {
  try {
    const ip = request.headers.get('x-forwarded-for')?.split(',')[0] || request.headers.get('x-real-ip') || '127.0.0.1';
    
    // Rygorystyczny Rate-Limiter (Max X zapytań na okno czasowe)
    const now = Date.now();
    const lastRequest = rateLimitMap.get(ip);
    const WINDOW_MS = 5 * 60 * 1000; // 5 minut

    if (lastRequest && now - lastRequest < WINDOW_MS) {
      console.warn(`[API Waitlist] Rate limited IP: ${ip}`);
      return new Response(JSON.stringify({ error: 'Za dużo prób w krótkim czasie. Odczekaj chwilę.' }), {
        status: 429, headers: { 'Content-Type': 'application/json' },
      });
    }
    
    if (rateLimitMap.size > 1000) rateLimitMap.clear();
    rateLimitMap.set(ip, now);

    const body = await request.json();
    const { firstName, lastName, email, phone, emailsPerDay } = body;

    // Basic validation
    if (!firstName || !lastName || !email) {
      return new Response(
        JSON.stringify({ error: 'Imię, nazwisko i email są wymagane.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Email format check
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return new Response(
        JSON.stringify({ error: 'Podaj prawidłowy adres email.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
    const payloadApiKey = import.meta.env.PAYLOAD_API_KEY;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Use API Key if configured
    if (payloadApiKey) {
      headers['Authorization'] = `users API-Key ${payloadApiKey}`;
    }

    const res = await fetch(`${payloadUrl}/api/waitlist-entries`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        email: email.trim().toLowerCase(),
        phone: phone?.trim() || '',
        emailsPerDay: emailsPerDay ? parseInt(emailsPerDay) : undefined,
      }),
    });

    if (!res.ok) {
      const errorText = await res.text();
      console.error('[Waitlist API] Payload error:', errorText);
      return new Response(
        JSON.stringify({ error: 'Nie udało się zapisać. Spróbuj ponownie.' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const result = await res.json();
    console.log('[Waitlist API] Zapisano:', result.doc?.email || email);

    return new Response(
      JSON.stringify({ success: true, message: 'Zostałeś dodany do listy oczekujących!' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  } catch (err: any) {
    console.error('[Waitlist API] Error:', err);
    return new Response(
      JSON.stringify({ error: err.message || 'Wystąpił błąd serwera.' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};
