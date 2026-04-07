import type { APIRoute } from 'astro';
import crypto from 'node:crypto';

export const prerender = false;

// Funkcja symetrycznego, tymczasowego szyfrowania (AES-256-GCM) do przekazania tokenu na frontend
const getTempKey = () => crypto.createHash('sha256').update(import.meta.env.OAUTH_TEMP_KEY || process.env.OAUTH_TEMP_KEY || 'dev_insecure_key_change_me').digest();

function encryptTemp(text: string): string {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-gcm', getTempKey(), iv);
  let enc = cipher.update(text, 'utf8', 'hex');
  enc += cipher.final('hex');
  const tag = cipher.getAuthTag().toString('hex');
  return `TEMP_ENC:${iv.toString('hex')}:${tag}:${enc}`;
}

export const GET: APIRoute = async ({ request, cookies, url }) => {
  const code = url.searchParams.get('code');
  const returnedState = url.searchParams.get('state');
  const expectedStateCookie = cookies.get('oauth_state')?.value;

  if (!code || !returnedState) {
    return new Response('Brak kodu lub parametru state.', { status: 400 });
  }

  // Odczytanie providera z returnedState (np. "google|xyz123")
  const [provider, stateValue] = returnedState.split('|');

  // Walidacja CSRF
  if (!expectedStateCookie || expectedStateCookie !== stateValue) {
    return new Response('Błąd weryfikacji CSRF. Spróbuj ponownie.', { status: 403 });
  }

  // Czyścimy ciasteczko state (single-use)
  cookies.delete('oauth_state', { path: '/api/oauth/' });

  const baseUrl = import.meta.env.SITE_URL || import.meta.env.SITE || 'http://localhost:4321';
  const redirectUri = `${baseUrl.replace(/\/$/, '')}/api/oauth/callback`;

  let email = '';
  let refreshToken = '';

  try {
    if (provider === 'google') {
      const clientId = import.meta.env.GOOGLE_CLIENT_ID || process.env.GOOGLE_CLIENT_ID || '';
      const clientSecret = import.meta.env.GOOGLE_CLIENT_SECRET || process.env.GOOGLE_CLIENT_SECRET || '';

      const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          code,
          client_id: clientId,
          client_secret: clientSecret,
          redirect_uri: redirectUri,
          grant_type: 'authorization_code',
        }),
      });

      const tokenData = await tokenRes.json();
      if (!tokenRes.ok) throw new Error(`Google Token Error: ${JSON.stringify(tokenData)}`);

      refreshToken = tokenData.refresh_token; 
      
      // Jeżeli użytkownik już wcześniej autoryzował aplikację, Google może nie zwrócić refresh_tokenu, 
      // dla pewności używamy prompt=consent w init, więc zazwyczaj powinien tu być.
      if (!refreshToken) {
         // Fallback - jeśli brak, oznacza to, że aplikacja ma już stały dostęp (wymaga revoke w koncie Google).
         refreshToken = 'ALREADY_GRANTED_OR_MISSING';
      }

      // Zdobycie adresu email (najprościej z id_token)
      if (tokenData.id_token) {
        const payloadBase64 = tokenData.id_token.split('.')[1];
        const decodedPayload = JSON.parse(Buffer.from(payloadBase64, 'base64').toString('utf8'));
        email = decodedPayload.email || '';
      }

    } else if (provider === 'microsoft') {
      const clientId = import.meta.env.MICROSOFT_CLIENT_ID || process.env.MICROSOFT_CLIENT_ID || '';
      const clientSecret = import.meta.env.MICROSOFT_CLIENT_SECRET || process.env.MICROSOFT_CLIENT_SECRET || '';

      const tokenRes = await fetch('https://login.microsoftonline.com/common/oauth2/v2.0/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: clientId,
          scope: 'offline_access Mail.Send Mail.ReadWrite',
          code,
          redirect_uri: redirectUri,
          grant_type: 'authorization_code',
          client_secret: clientSecret,
        }),
      });

      const tokenData = await tokenRes.json();
      if (!tokenRes.ok) throw new Error(`Microsoft Token Error: ${JSON.stringify(tokenData)}`);

      refreshToken = tokenData.refresh_token || '';

      if (tokenData.id_token) {
        const payloadBase64 = tokenData.id_token.split('.')[1];
        const decodedPayload = JSON.parse(Buffer.from(payloadBase64, 'base64').toString('utf8'));
        email = decodedPayload.preferred_username || decodedPayload.email || '';
      }
    } else {
      throw new Error('Unknown provider');
    }

    // Bezpieczne, tymczasowe zaszyfrowanie tokenu sebelum wyślemy go do przeglądarki!
    const encryptedToken = encryptTemp(refreshToken);

    // Przekazanie via postMessage do oryginalnego okna onboardingu (window.opener)
    // UWAGA: XSS/CORS Mitigation - targetOrigin musi być znany.
    const targetOrigin = baseUrl.startsWith('http') ? baseUrl : `https://${baseUrl}`;

    const htmlTemplate = `
      <!DOCTYPE html>
      <html>
      <head>
          <title>Autoryzacja zakończona</title>
      </head>
      <body>
          <p>Autoryzacja zakończona sukcesem. Zamykanie okna...</p>
          <script>
            // Bezpiecznie przekazujemy SZYFROGRAM do okna-rodzica
            if (window.opener) {
              window.opener.postMessage({
                type: 'OAUTH_SUCCESS',
                provider: '${provider}',
                email: '${email}',
                encryptedToken: '${encryptedToken}'
              }, '${targetOrigin.replace(/\/$/, '')}');
            }
            // Automatyczne zamknięcie popupu
            setTimeout(() => window.close(), 1000);
          </script>
      </body>
      </html>
    `;

    return new Response(htmlTemplate, {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });

  } catch (error: any) {
    console.error('Błąd OAuth Callback:', error);
    
    // W przypadku błędu też przekazujemy info do popupu, żeby zamknąć okienko z błędem
    const htmlTemplate = `
      <!DOCTYPE html>
      <html>
      <head>
          <title>Błąd autoryzacji</title>
      </head>
      <body>
          <p>Wystąpił błąd autoryzacji: ${error.message}</p>
          <button onclick="window.close()">Zamknij to okno</button>
          <script>
            if (window.opener) {
              window.opener.postMessage({
                type: 'OAUTH_ERROR',
                message: '${error.message.replace(/'/g, "\\'")}'
              }, '*');
            }
          </script>
      </body>
      </html>
    `;
    return new Response(htmlTemplate, { status: 400, headers: { 'Content-Type': 'text/html' }});
  }
};
