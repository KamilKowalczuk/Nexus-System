import type { APIRoute } from 'astro';
import Stripe from 'stripe';
import { verifySession } from '../../../utils/session';

export const prerender = false;

export const GET: APIRoute = async ({ request, cookies }) => {
  const sessionCookie = cookies.get('nexus_sub_session')?.value;
  const secret = import.meta.env.PAYLOAD_API_KEY;
  if (!secret) return new Response(JSON.stringify({ error: 'KRYTYCZNE NARUSZENIE: Brak klucza' }), { status: 500 });

  const orderId = verifySession(sessionCookie, secret);
  
  if (!orderId) {
    return new Response(JSON.stringify({ error: 'Nieautoryzowany dostęp.' }), { status: 401 });
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
    const searchRes = await fetch(`${payloadUrl}/api/orders/${orderId}?depth=1`, { headers: authHeaders });
    
    if (!searchRes.ok) {
      return new Response(JSON.stringify({ error: 'Błąd połączenia z bazą.' }), { status: 500 });
    }

    const order = await searchRes.json();
    
    let upcomingInvoice = null;
    let cancelAtDate = null;
    let liveCurrentPeriodEnd = order.currentPeriodEnd;

    // Jeżeli aktywna, dociągnij The Next Billing Date z API Stripe dla pięknego UX
    if (order.stripeSubscriptionId) {
        try {
            const stripeSecret = import.meta.env.STRIPE_SECRET_KEY;
            const stripe = new Stripe(stripeSecret!, { apiVersion: '2026-02-25.clover' } as any);
            
            const sub = await stripe.subscriptions.retrieve(order.stripeSubscriptionId) as any;
            
            cancelAtDate = sub.cancel_at ? new Date(sub.cancel_at * 1000).toISOString() : null;
            if (sub.current_period_end) {
                liveCurrentPeriodEnd = new Date(sub.current_period_end * 1000).toISOString();
            }
            
            if (sub.status === 'active' && !sub.cancel_at_period_end) {
                 try {
                     const inv = await (stripe.invoices as any).retrieveUpcoming({ subscription: sub.id });
                     if (inv && inv.next_payment_attempt) {
                         upcomingInvoice = {
                             amount_due: inv.amount_due / 100, // Stripe expects cents
                             next_payment_attempt: new Date(inv.next_payment_attempt * 1000).toISOString()
                         };
                     }
                 } catch (invErr) {
                     console.log('[dashboard-data] Brak wygenerowanej kolejnej faktury (często w Trybie Testowym):', invErr);
                 }
            }
        } catch (e) {
            console.error('[dashboard-data] Błąd pobierania ze Stripe:', e);
        }
    }

    // Bezpiecznie formatujemy dane na zewnątrz (ukrywamy krytyczne tokeny onboardingowe)
    const securePayload = {
        orderNumber: order.orderNumber,
        email: order.customerEmail,
        status: order.subscriptionStatus,
        dailyLimit: order.dailyLimit,
        monthlyAmount: order.monthlyAmount,
        currentPeriodEnd: liveCurrentPeriodEnd,
        cancelAtDate,
        upcomingInvoice,
        payments: order.payments || [],
        // Invoice data based off FakturaXL is embedded in payments.fakturaXlInvoiceId
    };

    return new Response(JSON.stringify(securePayload), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    console.error('[dashboard-data] Error:', err);
    return new Response(JSON.stringify({ error: 'Wystąpił nieoczekiwany błąd serwera.' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
};
