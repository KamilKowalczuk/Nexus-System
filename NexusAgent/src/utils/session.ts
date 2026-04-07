import crypto from 'node:crypto';

/**
 * Zwraca zdekodowany orderId, jeśli podpis (HMAC) w ciasteczku jest prawidłowy.
 * W przeciwnym razie zwraca null.
 */
export function verifySession(cookieValue: string | undefined, secret: string | undefined): string | null {
  if (!secret || secret === 'fallback_dev_secret_unsecure_!!') {
    throw new Error('KRYTYCZNY BŁĄD PROCESU: Brak klucza do autoryzacji sesji. Przerwanie by zapobiec atakom.');
  }

  if (!cookieValue) return null;
  const parts = cookieValue.split('.');
  if (parts.length !== 2) return null;
  
  const [orderId, signature] = parts;
  if (!orderId || !signature) return null;
  
  const expectedSignature = crypto.createHmac('sha256', secret).update(orderId).digest('hex');
  
  // compare() chroni przed timing attacks
  if (expectedSignature.length === signature.length && crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expectedSignature))) {
    return orderId;
  }
  
  return null;
}
