import type { APIRoute } from 'astro';
import crypto from 'node:crypto';

export const prerender = false;

const failedAttemptsMap = new Map<string, number>();

// Funkcja pomocnicza do budowy podpisu anty-fałszerstwo dla ciastka z sesją
export function signSessionId(orderId: string, secret: string): string {
  if (!secret || secret === 'fallback_dev_secret_unsecure_!!') {
    throw new Error('KRYTYCZNE NARUSZENIE KAKTU SESJI: Brak PAYLOAD_API_KEY');
  }
  return crypto.createHmac('sha256', secret).update(orderId).digest('hex');
}

export const POST: APIRoute = async ({ request, cookies, clientAddress }) => {
  const ip = clientAddress || '127.0.0.1';
  
  const failedCount = failedAttemptsMap.get(ip) || 0;
  if (failedCount >= 5) {
    return new Response(JSON.stringify({ error: 'Zbyt dużo błędnych prób. Odczekaj 15 minut ratelimitu.' }), {
      status: 429, headers: { 'Content-Type': 'application/json' },
    });
  }

  const body = await request.json();
  const { orderNumber, email, otp } = body as { orderNumber?: string; email?: string; otp?: string; };

  if (!orderNumber || !email || !otp) {
    return new Response(JSON.stringify({ error: 'Brakujące dane autoryzacyjne.' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  const authHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (apiKey) {
    authHeaders['Authorization'] = `users API-Key ${apiKey}`;
  }

  try {
    const searchRes = await fetch(
      `${payloadUrl}/api/orders?where[orderNumber][equals]=${encodeURIComponent(String(orderNumber).trim())}&limit=1&depth=0`,
      { headers: authHeaders }
    );
    
    if (!searchRes.ok) {
      return new Response(JSON.stringify({ error: 'Błąd połączenia z bazą.' }), { status: 500 });
    }

    const data = await searchRes.json();
    if (!data.docs || data.docs.length === 0) {
      return new Response(JSON.stringify({ error: 'Nieprawidłowy adres email lub nr zamówienia.' }), { status: 401 });
    }

    const order = data.docs[0];

    // Ochrona przed atakiem: sprawdzamy zgodność emaila
    if (order.customerEmail?.toLowerCase().trim() !== email.toLowerCase().trim()) {
      return new Response(JSON.stringify({ error: 'Nieprawidłowy adres email lub nr zamówienia.' }), { status: 401 });
    }

    // Walidacja istnienia kodu - OCHRONA PRZED TIMING ATTACKS
    const expectedOtp = String(order.otpCode || '').trim();
    const providedOtp = String(otp || '').trim();

    // timingSafeEqual wymaga buforów o tej samej długości
    const expectedBuffer = Buffer.from(expectedOtp);
    const providedBuffer = Buffer.from(providedOtp);

    let otpMatches = false;
    if (expectedBuffer.length === providedBuffer.length && expectedBuffer.length > 0) {
      otpMatches = crypto.timingSafeEqual(expectedBuffer, providedBuffer);
    }

    if (!otpMatches) {
      failedAttemptsMap.set(ip, failedCount + 1);
      setTimeout(() => failedAttemptsMap.delete(ip), 15 * 60 * 1000);
      return new Response(JSON.stringify({ error: 'Nieprawidłowy kod OTP. Upewnij się, że wpisujesz najnowszy.' }), { status: 401 });
    }

    // Walidacja czasu życia kodu
    if (!order.otpExpiry || new Date(order.otpExpiry) < new Date()) {
      return new Response(JSON.stringify({ error: 'Kod wygasł. Musisz wygenerować nowy.' }), { status: 401 });
    }

    // 1. Zwycięstwo! Kasujemy użyty OTP oraz błędy the Cache:
    failedAttemptsMap.delete(ip);
    await fetch(`${payloadUrl}/api/orders/${order.id}`, {
      method: 'PATCH',
      headers: authHeaders,
      body: JSON.stringify({ otpCode: null, otpExpiry: null }),
    });

    // 2. Osadzamy ciasteczko sesji
    // Ponieważ Payload nie zarządza naszymi sesjami w klasyczny sposób dla Klientów (mając tylko API keys admina),
    // zbudujemy proste HMAC podpisane przez payload api key
    if (!apiKey) {
      console.error('[verify-otp] PAYLOAD_API_KEY nie został odnaleziony w procesie autoryzacji sesji!');
      return new Response(JSON.stringify({ error: 'Wewnętrzny błąd konfiguracji uwierzytelniaczy kryptograficznych CSRF.' }), { status: 500 });
    }

    const sessionSecret = apiKey;
    const signature = signSessionId(String(order.id), sessionSecret);
    const cookieValue = `${order.id}.${signature}`;

    cookies.set('nexus_sub_session', cookieValue, {
      path: '/',
      httpOnly: true,
      secure: true, // Zawsze Secure w Panelu Zarządzania dla ochrony sesji
      sameSite: 'strict', // Ochrona przed CSRF
      maxAge: 60 * 60 * 2 // 2 godziny
    });

    return new Response(JSON.stringify({
      verified: true,
      orderId: order.id,
    }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    console.error('[verify-otp] Error:', err);
    return new Response(JSON.stringify({ error: 'Wewnętrzny błąd serwera.' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
};
