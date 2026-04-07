import type { APIRoute } from 'astro';
import Stripe from 'stripe';

export const prerender = false;


export const POST: APIRoute = async ({ request }) => {
  const stripeKey = import.meta.env.STRIPE_SECRET_KEY;
  const webhookSecret = import.meta.env.STRIPE_WEBHOOK_SECRET;

  if (!stripeKey || !webhookSecret) {
    console.error('[Stripe Webhook] Brak STRIPE_SECRET_KEY lub STRIPE_WEBHOOK_SECRET');
    return new Response('Stripe nie skonfigurowany', { status: 503 });
  }

  const stripe = new Stripe(stripeKey, { apiVersion: '2026-02-25.clover' });

  const body = await request.text();
  const signature = request.headers.get('stripe-signature');

  if (!signature) {
    return new Response('Brak podpisu Stripe', { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, webhookSecret);
  } catch (err: any) {
    console.error('[Stripe Webhook] Błąd weryfikacji podpisu:', err.message);
    console.error('[Stripe Webhook] Upewnij się, że STRIPE_WEBHOOK_SECRET zaczyna się od whsec_');
    return new Response(`Webhook Error: ${err.message}`, { status: 400 });
  }

  console.log(`[Stripe Webhook] Zdarzenie: ${event.type}`);
  const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
  const apiKey = import.meta.env.PAYLOAD_API_KEY;
  const authHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) authHeaders['Authorization'] = `users API-Key ${apiKey}`;

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session;

    const emailsPerDay = parseInt(session.metadata?.emailsPerDay || '20');
    const priceInPLN = parseInt(session.metadata?.priceInPLN || '1999');
    const customerEmail = session.customer_details?.email;
    const subscriptionId = session.subscription as string;

    console.log(`[Stripe Webhook] Nowy klient: ${customerEmail}`);
    console.log(`[Stripe Webhook] Plan: ${emailsPerDay} maili/dzień, ${priceInPLN} PLN/mc`);
    console.log(`[Stripe Webhook] Subscription ID: ${subscriptionId}`);

    try {
      const orderPayload = {
        clientEmail: customerEmail,
        stripeSubscriptionID: subscriptionId,
        stripeCustomerID: session.customer as string,
        emailsPerDay,
        status: 'active',
        monthlyAmount: priceInPLN,
      };

      const orderRes = await fetch(`${payloadUrl}/api/orders`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(orderPayload),
      });

      if (orderRes.ok) {
        console.log('[Stripe Webhook] Zamówienie zapisane do Payload CMS');
      } else {
        const errText = await orderRes.text();
        console.error(`[Stripe Webhook] Błąd zapisu zamówienia (${orderRes.status}):`, errText);
      }


    } catch (e) {
      console.error('[Stripe Webhook] Błąd połączenia z Payload:', e);
    }
  }

  if (event.type === 'customer.subscription.deleted') {
    const subscription = event.data.object as Stripe.Subscription;
    console.log(`[Stripe Webhook] Subskrypcja anulowana: ${subscription.id}`);

    try {
      const searchRes = await fetch(
        `${payloadUrl}/api/orders?where[stripeSubscriptionID][equals]=${subscription.id}&limit=1`,
        { headers: authHeaders }
      );

      if (searchRes.ok) {
        const searchData = await searchRes.json();
        if (searchData.docs?.length > 0) {
          const orderId = searchData.docs[0].id;
          await fetch(`${payloadUrl}/api/orders/${orderId}`, {
            method: 'PATCH',
            headers: authHeaders,
            body: JSON.stringify({ status: 'canceled' }),
          });
          console.log(`[Stripe Webhook] Zamówienie ${orderId} oznaczone jako anulowane`);
        }
      }


    } catch (e) {
      console.error('[Stripe Webhook] Błąd aktualizacji anulowanej subskrypcji:', e);
    }
  }

  return new Response(JSON.stringify({ received: true }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
};

