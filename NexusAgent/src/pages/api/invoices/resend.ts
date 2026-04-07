import type { APIRoute } from 'astro';
import { downloadInvoicePdf } from '../../../utils/fakturaXl';
import { dispatchInvoiceEmailWithPdf } from '../../../utils/emailInvoices';

export const prerender = false;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

export const OPTIONS: APIRoute = () => {
  return new Response(null, {
    status: 204,
    headers: corsHeaders,
  });
};

/**
 * POST /api/invoices/resend
 * Body: { fakturaXlInvoiceId: string }
 * Pobiera PDF z Faktura XL i ponownie wysyła emailem (szukając danych o kliencie w Payload).
 */
export const POST: APIRoute = async ({ request }) => {
  let body: { fakturaXlInvoiceId?: string } = {};

  try {
    body = await request.json();
  } catch {
    return new Response(
      JSON.stringify({ error: 'Nieprawidłowy JSON' }),
      { status: 400, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    );
  }

  const { fakturaXlInvoiceId } = body;

  if (!fakturaXlInvoiceId || fakturaXlInvoiceId.trim() === '') {
    return new Response(
      JSON.stringify({ error: 'Brak fakturaXlInvoiceId' }),
      { status: 400, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    );
  }

  const invoiceIdNum = parseInt(fakturaXlInvoiceId, 10);
  if (isNaN(invoiceIdNum) || invoiceIdNum <= 0) {
    return new Response(
      JSON.stringify({ error: 'Nieprawidłowy fakturaXlInvoiceId (musi być liczbą > 0)' }),
      { status: 400, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    );
  }

  // 1. Pobranie danych zamówienia z Payload w celu identyfikacji klienta do e-maila
  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  const authHeaders: Record<string, string> = apiKey ? { 'Authorization': `users API-Key ${apiKey}` } : {};

  // Szukamy zamówienia, którego payments zawiera dane ID
  const searchRes = await fetch(`${payloadUrl}/api/orders?where[payments.fakturaXlInvoiceId][equals]=${fakturaXlInvoiceId}&limit=1`, {
    headers: authHeaders
  });

  let orderNumber = 'BRAK';
  let email = '';
  let serviceName = 'Odnowienie subskrypcji NEXUS Agent';
  let amountGross = 0;

  if (searchRes.ok) {
    const data = await searchRes.json();
    if (data && data.docs && data.docs.length > 0) {
      const order = data.docs[0];
      orderNumber = order.orderNumber || 'BRAK';
      email = order.customerEmail;
      
      const paymentItem = order.payments?.find((p: any) => p.fakturaXlInvoiceId === fakturaXlInvoiceId);
      if (paymentItem) {
        amountGross = paymentItem.amount || order.monthlyAmount || 1999;
      } else {
        amountGross = order.monthlyAmount || 1999;
      }
      serviceName = `NEXUS Agent – ${order.dailyLimit || 20} maili/dzień – Plan miesięczny`;
    }
  }

  if (!email) {
    return new Response(
      JSON.stringify({ error: 'Nie odnaleziono powiązanego zamówienia i adresu email w bazie.' }),
      { status: 404, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    );
  }

  // 2. Pobierz PDF z Faktura XL
  const pdfBuffer = await downloadInvoicePdf(invoiceIdNum);

  if (!pdfBuffer) {
    return new Response(
      JSON.stringify({ error: 'Faktura XL zwróciła błąd podczas pobierania pliku PDF.' }),
      { status: 502, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    );
  }

  // 3. Wyślij mailem z użyciem Resend jako ponowna wysyłka (duplikat)
  const success = await dispatchInvoiceEmailWithPdf({
    toEmail: email,
    pdfBuffer,
    orderNumber,
    serviceName,
    amountGross,
    isResend: true,
  });

  if (!success) {
    return new Response(
      JSON.stringify({ error: 'Nieudana wysyłka wiadomości e-mail via Resend.' }),
      { status: 502, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    );
  }

  return new Response(
    JSON.stringify({ success: true, message: `Faktura ${fakturaXlInvoiceId} wygenerowana i wysłana (Resend).` }),
    { status: 200, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
  );
};
