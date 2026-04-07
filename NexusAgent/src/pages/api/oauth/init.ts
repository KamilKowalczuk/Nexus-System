import type { APIRoute } from 'astro';
import crypto from 'node:crypto';

export const prerender = false;

export const GET: APIRoute = async ({ request, cookies, url }) => {
  const provider = url.searchParams.get('provider');

  if (provider !== 'google' && provider !== 'microsoft') {
    return new Response('Nieprawidłowy dostawca OAuth', { status: 400 });
  }

  // Generowanie bezpiecznego tokenu przeciwko CSRF
  const state = crypto.randomBytes(32).toString('hex');
  
  // Zapis do bezpiecznego ciastka (tylko serwer, ważne 10 min)
  cookies.set('oauth_state', state, {
    httpOnly: true,
    secure: import.meta.env.PROD,
    sameSite: 'lax', // Musi być lax albo none, żeby wróciło z innego origin'u
    path: '/api/oauth/',
    maxAge: 600, // 10 minut
  });

  // Upewniamy się, że środowisko ma ustawiony poprawny base URL (w Astro: import.meta.env.SITE || własny env)
  const baseUrl = import.meta.env.SITE_URL || import.meta.env.SITE || 'http://localhost:4321';
  const redirectUri = `${baseUrl.replace(/\/$/, '')}/api/oauth/callback`;

  let authUrl = '';

  if (provider === 'google') {
    const clientId = import.meta.env.GOOGLE_CLIENT_ID || process.env.GOOGLE_CLIENT_ID || '';
    if (!clientId) return new Response('Brak konfiguracji Google', { status: 500 });

    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      scope: 'openid email https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.modify',
      access_type: 'offline', // Wymagane dla refresh_token w Google
      prompt: 'consent',      // Zmusza do ponownej zgody, aby zawsze wydać refresh_token
      state: `google|${state}`,
      include_granted_scopes: 'true',
    });
    authUrl = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  } 
  else if (provider === 'microsoft') {
    const clientId = import.meta.env.MICROSOFT_CLIENT_ID || process.env.MICROSOFT_CLIENT_ID || '';
    if (!clientId) return new Response('Brak konfiguracji Microsoft', { status: 500 });
    
    // Używamy endpointu "common", pozwalając na logowanie z kont osobistych oraz firmowych
    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      response_mode: 'query',
      scope: 'openid email offline_access Mail.Send Mail.ReadWrite', // offline_access jest tu kluczem dla refresh_token!
      state: `microsoft|${state}`,
      prompt: 'consent',
    });
    authUrl = `https://login.microsoftonline.com/common/oauth2/v2.0/authorize?${params.toString()}`;
  }

  // Konstruujemy Response ręcznie, aby Astro mogło dokleić nagłówki 'Set-Cookie'.
  // Użycie Response.redirect() tworzy obiekt z properties 'immutable', co crashuje Undici/Netlify.
  return new Response(null, {
    status: 302,
    headers: {
      Location: authUrl,
    },
  });
};
