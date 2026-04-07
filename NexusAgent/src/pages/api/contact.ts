import type { APIRoute } from 'astro';
import { Resend } from 'resend';

// Chroni przed HTML Injection w treści emailów wysyłanych do admina
function escapeHtml(str: unknown): string {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export const prerender = false;

const rateLimitMap = new Map<string, number>();

export const POST: APIRoute = async ({ request }) => {
  try {
    const ip = request.headers.get('x-forwarded-for')?.split(',')[0] || request.headers.get('x-real-ip') || '127.0.0.1';
    
    // Rygorystyczny Rate-Limiter (Max 2 maile na 10 minut na IP)
    const now = Date.now();
    const lastRequest = rateLimitMap.get(ip);
    const WINDOW_MS = 10 * 60 * 1000; 

    if (lastRequest && now - lastRequest < WINDOW_MS) {
      console.warn(`[API Contact] Rate limited IP: ${ip}`);
      return new Response(JSON.stringify({ error: 'Zbyt dużo zapytań. Spróbuj powonie za kilkanaście minut.' }), {
        status: 429, headers: { 'Content-Type': 'application/json' },
      });
    }
    
    // Cykliczne opróżnianie mapy chroniące przed Memory Leak
    if (rateLimitMap.size > 1000) rateLimitMap.clear();
    rateLimitMap.set(ip, now);

    const resendKey = import.meta.env.RESEND_API_KEY || process.env.RESEND_API_KEY;
    
    if (!resendKey) {
      console.error('[API Contact] Brak klucza RESEND_API_KEY');
      return new Response(
        JSON.stringify({ error: 'Błąd konfiguracji serwera (brak klucza API).' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const resend = new Resend(resendKey);
    const body = await request.json();

    // Honeypot check (jeśli bot_field jest wypełnione, to bot)
    if (body.bot_field) {
      console.log('[API Contact] Odrzucono przez honeypot');
      return new Response(
        JSON.stringify({ error: 'Zgłoszenie odrzucone (Honeypot).' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const { name, company, nip, phone, email, message, privacyConsent } = body;

    // Walidacja podstawowa na backendzie
    if (!name || !email || !phone || !message || !privacyConsent) {
      return new Response(
        JSON.stringify({ error: 'Brakujące pola wymagane.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Escapujemy wszystkie pola przed wstawieniem do HTML emaila
    const safeName    = escapeHtml(name);
    const safeCompany = escapeHtml(company);
    const safeNip     = escapeHtml(nip);
    const safePhone   = escapeHtml(phone);
    const safeEmail   = escapeHtml(email);
    const safeMessage = escapeHtml(message);

    // Odbiorca maila (Twój adres)
    const toEmail = import.meta.env.CONTACT_EMAIL || process.env.CONTACT_EMAIL || 'kontakt@nexusagent.pl';

    // Wysyłka przez Resend
    const { data, error } = await resend.emails.send({
      from: 'NEXUS System <onboarding@nexusagent.pl>',
      to: [toEmail],
      replyTo: email,
      subject: `[NEXUS LEAD] Nowe zgłoszenie od: ${safeName}${safeCompany ? ` (${safeCompany})` : ''}`,
      html: `
        <h2>Nowy lead z formularza NEXUS</h2>
        <p><strong>Imię i Nazwisko:</strong> ${safeName}</p>
        <p><strong>Email:</strong> ${safeEmail}</p>
        <p><strong>Telefon:</strong> ${safePhone}</p>
        <p><strong>Firma:</strong> ${safeCompany || 'Brak'}</p>
        <p><strong>NIP:</strong> ${safeNip || 'Brak'}</p>
        <p><strong>Zgoda na politykę:</strong> ${privacyConsent ? 'TAK' : 'NIE'}</p>
        <hr />
        <h3>Wiadomość:</h3>
        <p style="white-space: pre-wrap;">${safeMessage}</p>
      `,
    });

    if (error) {
      console.error('[API Contact] Resend Error:', error);
      return new Response(
        JSON.stringify({ error: `Błąd wysyłki: ${error.message}` }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }

    return new Response(
      JSON.stringify({ success: true, id: data?.id }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );

  } catch (err: any) {
    console.error('[API Contact] Catch Error:', err);
    return new Response(
      JSON.stringify({ error: 'Wewnętrzny błąd serwera. Spróbuj ponownie.' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};
