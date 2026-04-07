import type { APIRoute } from 'astro';
import { downloadInvoicePdf } from '../../../utils/fakturaXl';

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
 * GET /api/invoices/download?id=123
 * Pobiera dokument w formacie Base64 z Faktura XL, zamienia na Buffer i serwuje jako application/pdf.
 */
export const GET: APIRoute = async ({ request }) => {
  const url = new URL(request.url);
  const idStr = url.searchParams.get('id');

  if (!idStr) {
    return new Response('Brak parametru id', { status: 400, headers: corsHeaders });
  }

  const invoiceId = parseInt(idStr, 10);
  if (isNaN(invoiceId) || invoiceId <= 0) {
    return new Response('Nieprawidłowy ID faktury', { status: 400, headers: corsHeaders });
  }

  const pdfBuffer = await downloadInvoicePdf(invoiceId);

  if (!pdfBuffer) {
    return new Response('Nie udało się pobrać pliku PDF z systemu księgowego. ID mogło być błędne lub API odrzuciło żądanie.', { status: 404, headers: corsHeaders });
  }

  return new Response(new Uint8Array(pdfBuffer), {
    status: 200,
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': `inline; filename="Faktura-NEXUS-${invoiceId}.pdf"`,
      ...corsHeaders,
    },
  });
};
