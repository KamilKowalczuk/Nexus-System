import type { APIRoute } from 'astro';
import Stripe from 'stripe';
import { Resend } from 'resend';
import crypto from 'crypto';
import { createInvoice, downloadInvoicePdf, type FakturaXlClientData } from '../../../utils/fakturaXl';
import { dispatchInvoiceEmailWithPdf } from '../../../utils/emailInvoices';

export const prerender = false;

function generateOnboardingToken(): string {
  return crypto.randomBytes(32).toString('hex');
}

function buildOnboardingEmail(params: {
  customerEmail: string;
  token: string;
  dailyLimit: number;
  monthlyAmount: number;
  siteUrl: string;
  billingName: string;
  billingPhone: string;
  billingCompanyName: string;
  billingNip: string;
  billingStreet: string;
  billingCity: string;
  billingPostalCode: string;
  billingCountry: string;
  orderNumber: string;
}): { subject: string; html: string } {
  const { token, dailyLimit, monthlyAmount, siteUrl, billingName, billingPhone, billingCompanyName, billingNip, billingStreet, billingCity, billingPostalCode, billingCountry, orderNumber } = params;
  const link = `${siteUrl}/onboarding/${token}`;

  const hasBilling = billingCompanyName || billingNip || billingStreet;
  const billingHtml = hasBilling ? `
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(12,234,237,0.05);border:1px solid rgba(12,234,237,0.2);border-radius:12px;padding:16px;margin-bottom:24px;">
                <tr>
                  <td>
                    <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#0ceaed;margin-bottom:10px;">📋 Dane do faktury</div>
                    <div style="font-size:12px;color:#e2e8f0;line-height:1.8;">
                      ${billingName ? `<strong>Kontakt:</strong> ${billingName}${billingPhone ? ` · ${billingPhone}` : ''}<br/>` : ''}
                      ${billingCompanyName ? `<strong>Firma:</strong> ${billingCompanyName}<br/>` : ''}
                      ${billingNip ? `<strong>NIP:</strong> ${billingNip}<br/>` : ''}
                      ${billingStreet ? `<strong>Adres:</strong> ${billingStreet}, ${billingPostalCode} ${billingCity}${billingCountry && billingCountry !== 'PL' ? `, ${billingCountry}` : ''}<br/>` : ''}
                    </div>
                    <div style="font-size:10px;color:#64748b;margin-top:8px;">Dane zapisane automatycznie. Faktury będą generowane na powyższe dane.</div>
                  </td>
                </tr>
              </table>` : '';

  return {
    subject: 'NEXUS Agent – Twój jednorazowy link do konfiguracji systemu',
    html: `
<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NEXUS Agent – Onboarding</title>
</head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
              <img
                src="https://nexusagent.pl/logo.webp"
                alt="NEXUS Agent"
                width="120"
                height="120"
                style="display:block;margin:0 auto 12px auto;"
              />
              <div style="font-family:monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;margin-bottom:8px;">NEXUS AGENT</div>
              <div style="font-size:28px;font-weight:900;text-transform:uppercase;letter-spacing:-0.02em;color:#fff;">NEXUS Agent</div>
            </td>
          </tr>

          <!-- Main content -->
          <tr>
            <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">

              <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#0ceaed;margin-bottom:16px;">Dostęp aktywny</div>

              <h1 style="margin:0 0 16px;font-size:24px;font-weight:800;text-transform:uppercase;letter-spacing:-0.02em;color:#fff;line-height:1.2;">
                Płatność przyjęta.<br/>
                <span style="color:#0ceaed;">Poświęć nam jeszcze 15 minut</span>
              </h1>

              <p style="margin:0 0 24px;color:#94a3b8;font-size:14px;line-height:1.6;">
                Twoja subskrypcja NEXUS jest aktywna. Żeby ruszyć, potrzebujemy od Ciebie kilku informacji o tym,
                kogo szukamy i co im zaoferujemy. Cały formularz zajmuje 10–15 minut.
              </p>

              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:20px;margin-bottom:24px;">
                <tr>
                  <td style="padding:8px 16px;border-bottom:1px solid rgba(255,255,255,0.05);">
                    <span style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;">Wiadomości dziennie</span><br/>
                    <span style="font-size:18px;font-weight:700;color:#fff;">${dailyLimit} maili / dzień</span>
                  </td>
                  <td style="padding:8px 16px;border-bottom:1px solid rgba(255,255,255,0.05);text-align:right;">
                    <span style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;">Miesięczny abonament</span><br/>
                    <span style="font-size:18px;font-weight:700;color:#a855f7;">${monthlyAmount.toLocaleString('pl-PL')} PLN / mc</span>
                  </td>
                </tr>
                <tr>
                  <td colspan="2" style="padding:8px 16px;">
                    <span style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;">Status</span><br/>
                     <span style="font-size:14px;font-weight:600;color:#22c55e;">● Aktywna</span>
                  </td>
                </tr>
              </table>

              ${billingHtml}

              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(12,234,237,0.04);border:1px solid rgba(12,234,237,0.15);border-radius:12px;padding:16px;margin-bottom:24px;">
                <tr>
                  <td>
                    <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#0ceaed;margin-bottom:6px;">Numer zamówienia</div>
                    <div style="font-size:20px;font-weight:800;font-family:monospace;color:#fff;letter-spacing:0.1em;">${orderNumber || 'Generowany...'}</div>
                    <div style="font-size:10px;color:#64748b;margin-top:6px;">Zapisz ten numer – będzie potrzebny, jeśli zechcesz zmienić dane lub poprosić o nowy link do formularza.</div>
                  </td>
                </tr>
              </table>

              <div style="text-align:center;margin-bottom:32px;">
                <a href="${link}"
                   style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;font-weight:800;font-size:14px;text-transform:uppercase;letter-spacing:0.1em;padding:16px 40px;border-radius:100px;text-decoration:none;box-shadow:0 0 30px rgba(168,85,247,0.4);">
                   Otwórz formularz konfiguracji
                </a>
              </div>

              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(168,85,247,0.05);border:1px solid rgba(168,85,247,0.2);border-radius:12px;padding:16px;margin-bottom:24px;">
                <tr>
                  <td>
                    <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#a855f7;margin-bottom:8px;">🔐 Bezpieczeństwo</div>
                    <div style="font-size:12px;color:#94a3b8;line-height:1.5;">
                       Ten link działa tylko <strong style="color:#e2e8f0;">raz</strong> i wygasa po wypełnieniu formularza.
                       Jeśli nie składałeś zamówienia, możesz zignorować tę wiadomość.
                     </div>
                  </td>
                </tr>
              </table>

              <div style="font-size:12px;color:#64748b;line-height:1.8;">
                <div style="margin-bottom:6px;"><span style="color:#0ceaed;font-family:monospace;">01</span> &nbsp; Otwierasz link i potwierdzasz tożsamość kodem z maila</div>
                <div style="margin-bottom:6px;"><span style="color:#0ceaed;font-family:monospace;">02</span> &nbsp; Wypełniasz formularz (10–15 minut)</div>
                <div style="margin-bottom:6px;"><span style="color:#0ceaed;font-family:monospace;">03</span> &nbsp; Przygotowujemy kampanię (24–48h)</div>
                <div><span style="color:#0ceaed;font-family:monospace;">04</span> &nbsp; NEXUS zaczyna pisać do Twoich potencjalnych klientów</div>
              </div>

            </td>
          </tr>

          <tr>
            <td style="padding:24px 40px;text-align:center;">
              <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#334155;">
                NEXUS AGENT v2.4 · nexusagent.pl · Wsparcie: kontakt@nexusagent.pl
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `,
  };
}

// ─── Helper: generuj fakturę i uzupełnij wpis payments ───────────────────────
// WAŻNE: Ta funkcja musi być AWAJTOWANA przez wywołującego.
// Fire-and-forget nie działa w Netlify/serverless – środowisko ginie po return.

async function generateAndAttachInvoice(params: {
  orderId: string;
  orderNumber: string;
  paymentIndex: number;
  existingPayments: any[];
  clientData: FakturaXlClientData;
  dailyLimit: number;
  monthlyAmount: number;
  payloadUrl: string;
  authHeaders: Record<string, string>;
}): Promise<void> {
  const {
    orderId, orderNumber, paymentIndex, existingPayments,
    clientData, dailyLimit, monthlyAmount, payloadUrl, authHeaders,
  } = params;

  try {
    const invoice = await createInvoice({
      client: clientData,
      orderNumber,
      serviceName: `NEXUS Agent – ${dailyLimit} maili/dzień – Plan miesięczny`,
      totalPriceGross: monthlyAmount,
      isVatExempt: true,
      vatExemptionBasis: 'Zwolnienie z VAT na podstawie art. 113 ust. 1 i 9 ustawy o VAT',
    });

    if (!invoice || !invoice.id) {
      console.error('[Webhook] Faktura XL: nie udało się wygenerować faktury dla order', orderNumber);
      return;
    }

    // Pobierz PDF faktury jako Buffer
    const pdfBuffer = await downloadInvoicePdf(invoice.id);
    let emailSent = false;

    if (pdfBuffer) {
      // Wyślij PDF za pomocą Resend
      emailSent = await dispatchInvoiceEmailWithPdf({
        toEmail: clientData.email,
        pdfBuffer,
        orderNumber,
        serviceName: `NEXUS Agent – ${dailyLimit} maili/dzień – Plan miesięczny`,
        amountGross: monthlyAmount,
      });

      if (!emailSent) {
        console.warn('[Webhook] Invoice Email Dispatch: wysyłka emaila nieudana dla faktury XL ID', invoice.id);
      }
    } else {
      console.warn('[Webhook] Faktura XL: błąd pobierania PDF-a dla faktury XL ID', invoice.id);
    }

    // Uzupełnij wpis payments o dane faktury
    const updatedPayments = [...existingPayments];
    if (updatedPayments[paymentIndex]) {
      updatedPayments[paymentIndex] = {
        ...updatedPayments[paymentIndex],
        fakturaXlInvoiceId: String(invoice.id),
        invoiceStatus: emailSent ? 'sent' : 'error',
      };
    }

    const patchRes = await fetch(`${payloadUrl}/api/orders/${orderId}`, {
      method: 'PATCH',
      headers: authHeaders,
      body: JSON.stringify({ payments: updatedPayments }),
    });

    if (!patchRes.ok) {
      console.error('[Webhook] PATCH payments failed:', patchRes.status, await patchRes.text());
      return;
    }

    console.log(`[Webhook] Faktura XL: faktura ${invoice.id} wygenerowana i obsłużona dla order ${orderNumber}`);
  } catch (err) {
    console.error('[Webhook] generateAndAttachInvoice error:', err);
  }
}

function buildCancellationEmail(params: {
  customerEmail: string;
  orderNumber: string;
  siteUrl: string;
}): { subject: string; html: string } {
  const { orderNumber, siteUrl } = params;
  return {
    subject: 'NEXUS Agent – Subskrypcja anulowana',
    html: `
<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /></head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
          <tr>
            <td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
              <img src="https://nexusagent.pl/logo.webp" alt="NEXUS Agent" width="80" height="80" style="display:block;margin:0 auto 12px auto;" />
              <div style="font-family:monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;margin-bottom:8px;">NEXUS AGENT</div>
            </td>
          </tr>
          <tr>
            <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">
              <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#ef4444;margin-bottom:16px;">Subskrypcja zakończona</div>
              <h1 style="margin:0 0 16px;font-size:22px;font-weight:800;color:#fff;line-height:1.3;">
                Twoja subskrypcja NEXUS<br/>
                <span style="color:#ef4444;">została anulowana.</span>
              </h1>
              <p style="margin:0 0 24px;color:#94a3b8;font-size:14px;line-height:1.6;">
                Kampania AI została zatrzymana. Jeśli to Ty anulowałeś — nie musisz nic robić.
                Jeśli to pomyłka lub chcesz wrócić, napisz do nas.
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:20px;margin-bottom:24px;">
                <tr>
                  <td>
                    <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;">Numer zamówienia</div>
                    <div style="font-size:18px;font-weight:700;font-family:monospace;color:#fff;margin-top:4px;">${orderNumber}</div>
                  </td>
                  <td style="text-align:right;">
                    <span style="font-size:13px;font-weight:600;color:#ef4444;">● Anulowana</span>
                  </td>
                </tr>
              </table>
              <div style="text-align:center;margin-bottom:24px;">
                <a href="mailto:kontakt@nexusagent.pl"
                   style="display:inline-block;background:rgba(255,255,255,0.05);color:#e2e8f0;font-weight:600;font-size:13px;padding:12px 28px;border-radius:100px;text-decoration:none;border:1px solid rgba(255,255,255,0.1);">
                  Skontaktuj się z nami
                </a>
              </div>
              <div style="text-align:center;">
                <a href="${siteUrl}/#pricing"
                   style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:0.08em;padding:12px 28px;border-radius:100px;text-decoration:none;">
                  Wróć do NEXUS
                </a>
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 40px;text-align:center;">
              <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#334155;">
                NEXUS AGENT · nexusagent.pl · Wsparcie: kontakt@nexusagent.pl
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`,
  };
}

function buildPaymentFailedEmail(params: {
  orderNumber: string;
  dailyLimit: number;
  monthlyAmount: number;
  siteUrl: string;
}): { subject: string; html: string } {
  const { orderNumber, dailyLimit, monthlyAmount, siteUrl } = params;
  return {
    subject: 'NEXUS Agent – Problem z płatnością – wymagane działanie',
    html: `
<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /></head>
<body style="margin:0;padding:0;background:#050508;font-family:'Inter',sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050508;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
          <tr>
            <td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.06);">
              <img src="https://nexusagent.pl/logo.webp" alt="NEXUS Agent" width="80" height="80" style="display:block;margin:0 auto 12px auto;" />
              <div style="font-family:monospace;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#0ceaed;margin-bottom:8px;">NEXUS AGENT</div>
            </td>
          </tr>
          <tr>
            <td style="padding:40px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:24px;margin-top:16px;">
              <div style="font-size:11px;font-family:monospace;text-transform:uppercase;letter-spacing:0.2em;color:#f59e0b;margin-bottom:16px;">⚠ Wymagane działanie</div>
              <h1 style="margin:0 0 16px;font-size:22px;font-weight:800;color:#fff;line-height:1.3;">
                Nie udało się pobrać<br/>
                <span style="color:#f59e0b;">opłaty za subskrypcję.</span>
              </h1>
              <p style="margin:0 0 24px;color:#94a3b8;font-size:14px;line-height:1.6;">
                Stripe nie mógł obciążyć Twojej karty. Kampania AI działa normalnie,
                ale Stripe ponowi próbę w ciągu kilku dni. Jeśli płatność nie przejdzie — subskrypcja zostanie automatycznie anulowana.
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" style="background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.25);border-radius:16px;padding:20px;margin-bottom:24px;">
                <tr>
                  <td style="padding:6px 12px;border-bottom:1px solid rgba(255,255,255,0.05);">
                    <span style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;">Zamówienie</span><br/>
                    <span style="font-size:16px;font-weight:700;font-family:monospace;color:#fff;">${orderNumber}</span>
                  </td>
                  <td style="padding:6px 12px;border-bottom:1px solid rgba(255,255,255,0.05);text-align:right;">
                    <span style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;">Plan</span><br/>
                    <span style="font-size:14px;font-weight:600;color:#fff;">${dailyLimit} maili / dzień</span>
                  </td>
                </tr>
                <tr>
                  <td colspan="2" style="padding:6px 12px;">
                    <span style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#64748b;">Kwota do zapłaty</span><br/>
                    <span style="font-size:16px;font-weight:700;color:#f59e0b;">${monthlyAmount.toLocaleString('pl-PL')} PLN</span>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 20px;color:#94a3b8;font-size:13px;line-height:1.6;">
                Zaktualizuj dane płatnicze w panelu Stripe, żeby uniknąć przerwy w kampanii.
              </p>
              <div style="text-align:center;margin-bottom:16px;">
                <a href="${siteUrl}/manage-subscription"
                   style="display:inline-block;background:linear-gradient(135deg,#d97706,#f59e0b);color:#000;font-weight:800;font-size:14px;text-transform:uppercase;letter-spacing:0.08em;padding:14px 36px;border-radius:100px;text-decoration:none;">
                  Zaktualizuj metodę płatności
                </a>
              </div>
              <div style="text-align:center;">
                <a href="mailto:kontakt@nexusagent.pl" style="font-size:12px;color:#64748b;text-decoration:underline;">Masz pytania? Napisz do nas</a>
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 40px;text-align:center;">
              <div style="font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:0.15em;color:#334155;">
                NEXUS AGENT · nexusagent.pl · Wsparcie: kontakt@nexusagent.pl
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`,
  };
}

export const POST: APIRoute = async ({ request }) => {
  const stripeKey = import.meta.env.STRIPE_SECRET_KEY;
  const webhookSecret = import.meta.env.STRIPE_WEBHOOK_SECRET;

  if (!stripeKey || !webhookSecret) {
    return new Response('Stripe nie skonfigurowany', { status: 503 });
  }

  const stripe = new Stripe(stripeKey, { apiVersion: '2026-02-25.clover' });

  const body = await request.text();
  const signature = request.headers.get('stripe-signature');
  if (!signature) return new Response('Brak podpisu', { status: 400 });

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, webhookSecret);
  } catch (err: any) {
    console.error('[Webhook Stripe] Błąd weryfikacji:', err.message);
    return new Response(`Webhook Error: ${err.message}`, { status: 400 });
  }

  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const siteUrl = import.meta.env.SITE_URL || 'https://nexusagent.pl';
  const resendKey = import.meta.env.RESEND_API_KEY;
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  const authHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) authHeaders['Authorization'] = `users API-Key ${apiKey}`;

  // ─── checkout.session.completed ───────────────────────────────────────────
  // Zadanie: zapisz order z danymi klienta i wyślij email onboardingowy.
  // NIE tworzymy tutaj payments[] – invoice.payment_succeeded zrobi to automatycznie
  // z prawidłowym stripeInvoiceId i kwotą. Tworzyliśmy duplikaty (checkout + invoice).
  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session;

    // ─── IDEMPOTENCJA: Sprawdź czy to zamówienie już istnieje (na bazie event.id)
    const checkRes = await fetch(
      `${payloadUrl}/api/orders?where[stripeEventId][equals]=${String(event.id)}&limit=1`,
      { headers: authHeaders }
    );
    if (checkRes.ok) {
      const checkData = await checkRes.json();
      if (checkData.docs?.length > 0) {
        console.log(`[Webhook Stripe] Event ${event.id} już przetworzony (Order istnieje). Skip.`);
        return new Response('OK - Duplicate skipped', { status: 200 });
      }
    }

    const customerEmail = session.customer_details?.email;
    const dailyLimit = parseInt(String(session.metadata?.emailsPerDay || '20'));
    const monthlyAmount = parseInt(String(session.metadata?.priceInPLN || '1999'));
    const stripeCustomerId = session.customer as string;
    const stripeSubscriptionId = session.subscription as string;
    const onboardingToken = generateOnboardingToken();

    const customFields = (session as any).custom_fields || [];
    const nipField = customFields.find((f: any) => f.key === 'nip');
    const companyField = customFields.find((f: any) => f.key === 'company_name');

    const billingNip = nipField?.text?.value || '';
    const billingCompanyName = companyField?.text?.value || '';
    const billingName = session.customer_details?.name || '';
    const billingPhone = (session as any).customer_details?.phone || '';

    const address = session.customer_details?.address;
    const billingStreet = [address?.line1, address?.line2].filter(Boolean).join(', ') || '';
    const billingCity = address?.city || '';
    const billingPostalCode = address?.postal_code || '';
    const billingCountry = address?.country || 'PL';

    try {
      const stripeInvoiceId = typeof session.invoice === 'string' ? session.invoice : (session.invoice as any)?.id || '';

      // 1. Inicjalny wpis payments (z danymi faktury od Stripe)
      const initialPayment = {
        stripeInvoiceId,
        amount: monthlyAmount,
        paidAt: new Date().toISOString(),
        status: 'paid',
        fakturaXlInvoiceId: '',
        invoiceUrl: '',
        invoicePdf: '',
      };

      // Zapisz zamówienie do Payload z danymi fakturowymi
      // Inicjalizujemy payments pierwszym wpisem, ponieważ invoice.payment_succeeded
      // może przyjść przed zapisem orderu w bazie i zostać zignorowany.
      const orderRes = await fetch(`${payloadUrl}/api/orders`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          customerEmail,
          stripeCustomerId,
          stripeSubscriptionId,
          dailyLimit,
          monthlyAmount,
          subscriptionStatus: 'active',
          onboardingToken,
          payments: [initialPayment],
          billingName,
          billingPhone,
          billingCompanyName,
          billingNip,
          billingStreet,
          billingCity,
          billingPostalCode,
          billingCountry,
          stripeEventId: String(event.id), // Zapisz ID eventu dla idempotencji
        }),
      });

      if (!orderRes.ok) {
        console.error('[Webhook Stripe] Błąd zapisu Order:', await orderRes.text());
      }

      // Odczytaj orderNumber i id z zapisanego dokumentu
      let orderNumber = '';
      let orderId = '';
      try {
        const orderBody = await orderRes.json();
        orderNumber = orderBody?.doc?.orderNumber || orderBody?.orderNumber || '';
        orderId = orderBody?.doc?.id || orderBody?.id || '';
      } catch { /* ignoruj */ }

      // ─── Generuj pierwszą fakturę Faktura XL ──────────────────────────────
      if (customerEmail && orderId && orderNumber) {
        const clientData: FakturaXlClientData = {
          companyName: billingCompanyName || billingName || customerEmail,
          firstName: !billingCompanyName ? billingName.split(' ')[0] : '',
          lastName: !billingCompanyName ? billingName.split(' ').slice(1).join(' ') : '',
          email: customerEmail,
          taxNo: billingNip,
          street: billingStreet,
          city: billingCity,
          postCode: billingPostalCode,
          country: billingCountry,
          phone: billingPhone,
        };

        // KRYTYCZNE: await, serverless ginie przy return
        await generateAndAttachInvoice({
          orderId,
          orderNumber,
          paymentIndex: 0,
          existingPayments: [initialPayment],
          clientData,
          dailyLimit,
          monthlyAmount,
          payloadUrl,
          authHeaders,
        });
      }



      // Wyślij email onboardingowy przez Resend
      if (resendKey && customerEmail) {
        const resend = new Resend(resendKey);
        const { subject, html } = buildOnboardingEmail({
          customerEmail,
          token: onboardingToken,
          dailyLimit,
          monthlyAmount,
          siteUrl,
          billingName,
          billingPhone,
          billingCompanyName,
          billingNip,
          billingStreet,
          billingCity,
          billingPostalCode,
          billingCountry,
          orderNumber,
        });

        const emailResult = await resend.emails.send({
          from: 'NEXUS Agent <onboarding@nexusagent.pl>',
          to: customerEmail,
          subject,
          html,
        });

        if (emailResult.error) {
          console.error('[Webhook Stripe] Błąd wysyłki emaila:', emailResult.error);
        }
      }
    } catch (err) {
      console.error('[Webhook Stripe] Błąd ogólny checkout:', err);
    }
  }

  // ─── invoice.payment_succeeded ────────────────────────────────────────────
  // Zadanie: dodaj wpis do payments[] + wygeneruj fakturę przez Fakturownia.
  // Dotyczy zarówno pierwszej płatności jak i kolejnych (subskrypcja cykliczna).
  // KLUCZOWE: await generateAndAttachInvoice() – serverless ginie przy return!
  if (event.type === 'invoice.payment_succeeded') {
    const invoice = event.data.object as Stripe.Invoice;
    const subscriptionId = (invoice as any).subscription as string;
    const periodEnd = (invoice as any).lines?.data?.[0]?.period?.end;
    const periodStart = (invoice as any).lines?.data?.[0]?.period?.start;

    if (subscriptionId) {
      try {
        const searchRes = await fetch(
          `${payloadUrl}/api/orders?where[stripeSubscriptionId][equals]=${String(subscriptionId)}&limit=1`,
          { headers: authHeaders }
        );

        if (searchRes.ok) {
          const searchData = await searchRes.json();
          if (searchData.docs?.length > 0) {
            const order = searchData.docs[0];
            const orderId: string = order.id;
            const orderNumber: string = order.orderNumber || '';
            const customerEmail: string = order.customerEmail || '';
            const existingPayments: any[] = order.payments || [];

            // Zabezpieczenie przed duplikatem: sprawdź czy płatność o tym stripeInvoiceId już istnieje LUB event był procesowany
            const eventProcessed = (order.processedEvents || []).some((e: any) => e.eventId === event.id);
            if (existingPayments.some((p) => p.stripeInvoiceId === invoice.id) || eventProcessed) {
              console.log(`[Webhook Stripe] Event ${event.id} (faktura ${invoice.id}) już przetworzony. Skip.`);
              return new Response(JSON.stringify({ received: true, note: 'Duplicate' }), {
                status: 200, headers: { 'Content-Type': 'application/json' }
              });
            }

            const updatedProcessedEvents = [...(order.processedEvents || []), { eventId: String(event.id) }];

            // Nowy wpis payment
            const newPayment = {
              stripeInvoiceId: invoice.id,
              amount: Math.round(((invoice as any).amount_paid || 0) / 100),
              paidAt: new Date().toISOString(),
              status: 'paid',
              fakturaXlInvoiceId: '',
              ...(periodStart ? { periodStart: new Date(periodStart * 1000).toISOString() } : {}),
              ...(periodEnd ? { periodEnd: new Date(periodEnd * 1000).toISOString() } : {}),
            };

            const updatedPayments = [...existingPayments, newPayment];
            const newPaymentIndex = updatedPayments.length - 1;

            // Zapisz payments (bez faktury na razie)
            await fetch(`${payloadUrl}/api/orders/${orderId}`, {
              method: 'PATCH',
              headers: authHeaders,
              body: JSON.stringify({
                subscriptionStatus: 'active',
                payments: updatedPayments,
                processedEvents: updatedProcessedEvents, // Idempotencja
                ...(periodEnd ? { currentPeriodEnd: new Date(periodEnd * 1000).toISOString() } : {}),
              }),
            });

            // Generuj fakturę i uzupełnij payments – MUSI być await przed return!
            if (customerEmail && orderId && orderNumber) {
              const clientData: FakturaXlClientData = {
                companyName: order.billingCompanyName || order.billingName || customerEmail,
                firstName: !order.billingCompanyName ? (order.billingName || '').split(' ')[0] : '',
                lastName: !order.billingCompanyName ? (order.billingName || '').split(' ').slice(1).join(' ') : '',
                email: customerEmail,
                taxNo: order.billingNip || '',
                street: order.billingStreet || '',
                city: order.billingCity || '',
                postCode: order.billingPostalCode || '',
                country: order.billingCountry || 'PL',
                phone: order.billingPhone || '',
              };

              await generateAndAttachInvoice({
                orderId,
                orderNumber,
                paymentIndex: newPaymentIndex,
                existingPayments: updatedPayments,
                clientData,
                dailyLimit: order.dailyLimit || 20,
                monthlyAmount: Math.round(((invoice as any).amount_paid || 0) / 100) || order.monthlyAmount || 1999,
                payloadUrl,
                authHeaders,
              });
            }
          }
        }
      } catch (err) {
        console.error('[Webhook Stripe] Błąd aktualizacji invoice:', err);
      }
    }
  }

  // ─── customer.subscription.deleted ───────────────────────────────────────
  if (event.type === 'customer.subscription.deleted') {
    const subscription = event.data.object as Stripe.Subscription;
    try {
      const searchRes = await fetch(
        `${payloadUrl}/api/orders?where[stripeSubscriptionId][equals]=${subscription.id}&limit=1`,
        { headers: authHeaders }
      );
      if (searchRes.ok) {
        const data = await searchRes.json();
        if (data.docs?.length > 0) {
          const order = data.docs[0];
          await fetch(`${payloadUrl}/api/orders/${order.id}`, {
            method: 'PATCH',
            headers: authHeaders,
            body: JSON.stringify({ subscriptionStatus: 'canceled' }),
          });
          console.log(`[Webhook Stripe] Zamówienie anulowane dla subskrypcji: ${subscription.id}`);

          if (resendKey && order.customerEmail) {
            const resend = new Resend(resendKey);
            const { subject, html } = buildCancellationEmail({
              customerEmail: order.customerEmail,
              orderNumber: order.orderNumber || order.id,
              siteUrl,
            });
            await resend.emails.send({
              from: 'NEXUS Agent <onboarding@nexusagent.pl>',
              to: order.customerEmail,
              subject,
              html,
            });
          }
        }
      }
    } catch (err) {
      console.error('[Webhook Stripe] Błąd anulowania subskrypcji:', err);
    }
  }

  // ─── invoice.payment_failed ───────────────────────────────────────────────
  if (event.type === 'invoice.payment_failed') {
    const invoice = event.data.object as Stripe.Invoice;
    const subscriptionId = (invoice as any).subscription as string;
    if (subscriptionId) {
      try {
        const searchRes = await fetch(
          `${payloadUrl}/api/orders?where[stripeSubscriptionId][equals]=${subscriptionId}&limit=1`,
          { headers: authHeaders }
        );
        if (searchRes.ok) {
          const data = await searchRes.json();
          if (data.docs?.length > 0) {
            const order = data.docs[0];
            await fetch(`${payloadUrl}/api/orders/${order.id}`, {
              method: 'PATCH',
              headers: authHeaders,
              body: JSON.stringify({ subscriptionStatus: 'past_due' }),
            });
            console.log(`[Webhook Stripe] Nieudana płatność dla subskrypcji: ${subscriptionId}`);

            if (resendKey && order.customerEmail) {
              const resend = new Resend(resendKey);
              const { subject, html } = buildPaymentFailedEmail({
                orderNumber: order.orderNumber || order.id,
                dailyLimit: order.dailyLimit,
                monthlyAmount: order.monthlyAmount,
                siteUrl,
              });
              await resend.emails.send({
                from: 'NEXUS Agent <onboarding@nexusagent.pl>',
                to: order.customerEmail,
                subject,
                html,
              });
            }
          }
        }
      } catch (err) {
        console.error('[Webhook Stripe] Błąd obsługi nieudanej płatności:', err);
      }
    }
  }

  return new Response(JSON.stringify({ received: true }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
};
