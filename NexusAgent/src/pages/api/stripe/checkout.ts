import type { APIRoute } from 'astro';
import Stripe from 'stripe';

export const prerender = false;

// Cena bazowa: 1999 PLN za 20 maili/dzień, +25 PLN za każdy dodatkowy mail
function calculatePrice(emailsPerDay: number): number {
  const base = 1999;
  const extra = Math.max(0, emailsPerDay - 20) * 25;
  return base + extra;
}

export const POST: APIRoute = async ({ request }) => {
  const stripeKey = import.meta.env.STRIPE_SECRET_KEY;

  if (!stripeKey || stripeKey === 'sk_test_REPLACE_ME') {
    return new Response(
      JSON.stringify({ error: 'Stripe nie jest skonfigurowany. Dodaj STRIPE_SECRET_KEY do .env' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }

  try {
    const body = await request.json();
    const emailsPerDay = Math.max(10, Math.min(100, parseInt(body.emailsPerDay) || 20));
    const priceInPLN = calculatePrice(emailsPerDay);
    const priceInGrosze = priceInPLN * 100; // Stripe operuje w groszach

    const stripe = new Stripe(stripeKey, { apiVersion: '2026-02-25.clover' });

    const successUrl = import.meta.env.STRIPE_SUCCESS_URL || 'http://localhost:4321/dziekujemy';
    const cancelUrl = import.meta.env.STRIPE_CANCEL_URL || 'http://localhost:4321/blad';

    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      mode: 'subscription',
      billing_address_collection: 'required',
      phone_number_collection: { enabled: true },
      custom_fields: [
        {
          key: 'nip',
          label: { type: 'custom', custom: 'NIP firmy (opcjonalnie)' },
          type: 'text',
          optional: true,
        },
        {
          key: 'company_name',
          label: { type: 'custom', custom: 'Nazwa firmy (do faktury)' },
          type: 'text',
          optional: true,
        },
      ],
      line_items: [
        {
          price_data: {
            currency: 'pln',
            recurring: { interval: 'month' },
            product_data: {
              name: `NEXUS Agent – ${emailsPerDay} maili/dzień`,
              description: `Automatyzacja cold email B2B: ${emailsPerDay} spersonalizowanych wiadomości dziennie, 24/7 autonomiczna praca, głęboki research AI.`,
              metadata: { emailsPerDay: emailsPerDay.toString() },
            },
            unit_amount: priceInGrosze,
          },
          quantity: 1,
        },
      ],
      metadata: {
        emailsPerDay: emailsPerDay.toString(),
        priceInPLN: priceInPLN.toString(),
      },
      success_url: `${successUrl}?session_id={CHECKOUT_SESSION_ID}&emails=${emailsPerDay}`,
      cancel_url: `${cancelUrl}?from=stripe`,
      locale: 'pl',
    });

    return new Response(JSON.stringify({ url: session.url }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err: any) {
    console.error('[Stripe Checkout] Error:', err);
    return new Response(
      JSON.stringify({ error: err.message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};
