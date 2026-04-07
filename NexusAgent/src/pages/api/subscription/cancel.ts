import type { APIRoute } from 'astro';
import Stripe from 'stripe';
import { Resend } from 'resend';
import { verifySession } from '../../../utils/session';

export const prerender = false;

export const POST: APIRoute = async ({ request, cookies }) => {
  const sessionCookie = cookies.get('nexus_sub_session')?.value;
  const secret = import.meta.env.PAYLOAD_API_KEY;
  if (!secret) return new Response(JSON.stringify({ error: 'KRYTYCZNY BŁĄD PROCESU: Brak the auth secret.' }), { status: 500 });

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
    // 1. Pobierz dane subskrypcji z Payloada
    const searchRes = await fetch(`${payloadUrl}/api/orders/${orderId}?depth=0`, { headers: authHeaders });
    
    if (!searchRes.ok) {
      return new Response(JSON.stringify({ error: 'Błąd połączenia z bazą.' }), { status: 500 });
    }

    const order = await searchRes.json();
    if (!order || !order.stripeSubscriptionId) {
      return new Response(JSON.stringify({ error: 'Brak aktywnej subskrypcji Stripe w zamówieniu.' }), { status: 400 });
    }

    if (order.subscriptionStatus === 'canceled') {
      return new Response(JSON.stringify({ error: 'Subskrypcja jest już anulowana.' }), { status: 400 });
    }

    // 2. Anuluj w Stripe API z zachowaniem okresu
    const stripeSecret = import.meta.env.STRIPE_SECRET_KEY;
    if (!stripeSecret) {
      return new Response(JSON.stringify({ error: 'Brak konfiguracji Stripe' }), { status: 500 });
    }

    const stripe = new Stripe(stripeSecret, {
      apiVersion: '2026-02-25.clover',
    });

    const updatedSubscription = await stripe.subscriptions.update(
      order.stripeSubscriptionId,
      {
        cancel_at_period_end: true,
      }
    );

    // 3. Zaktualizuj status w Payload CMS
    const patchRes = await fetch(`${payloadUrl}/api/orders/${order.id}`, {
      method: 'PATCH',
      headers: authHeaders,
      body: JSON.stringify({ 
        subscriptionStatus: 'canceled',
        cancelAtDate: new Date(updatedSubscription.cancel_at! * 1000).toISOString(),
      }),
    });

    if (!patchRes.ok) {
      console.error('[cancel-subscription] Błąd synchronizacji anulowania bazy Payload:', patchRes.statusText);
      // Nie rzucamy bledu frontendowi, bo w Stripe juz wylaczono, a Webhook ostatecznie to dogra
    }

    // 4. Send cancellation email
    const cancelDateStr = new Date(updatedSubscription.cancel_at! * 1000).toLocaleDateString('pl-PL', {
      year: 'numeric', month: 'long', day: 'numeric'
    });

    const resendKey = import.meta.env.RESEND_API_KEY || process.env.RESEND_API_KEY;
    if (resendKey) {
      const resend = new Resend(resendKey);
      await resend.emails.send({
        from: 'NEXUS Agent <onboarding@nexusagent.pl>',
        to: order.customerEmail,
        subject: `Potwierdzenie anulowania usługi NEXUS`,
        html: `
          <div style="background:#050508;padding:40px;font-family:monospace;color:#e2e8f0;border-radius:16px;">
            <div style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#ef4444;margin-bottom:16px;">NEXUS AGENT – ZMIANA STATUSU</div>
            <div style="font-size:18px;font-weight:bold;color:#f8fafc;margin-bottom:16px;">Twoja subskrypcja została anulowana</div>
            <div style="font-size:14px;color:#94a3b8;line-height:1.6;margin-bottom:24px;">
              Potwierdzamy zlecenie anulowania subskrypcji dla zamówienia <strong style="color:#fff;">${order.orderNumber}</strong>.<br><br>
              Usługa pozostaje w pełni aktywna do końca opłaconego okresu rozliczeniowego, czyli do:<br>
              <strong style="color:#0ceaed;font-size:16px;">${cancelDateStr}</strong>.<br><br>
              Po tym terminie infrastruktura agenta zostanie zgaszona (dane zostaną samoczynnie usunięte). Dziękujemy za współpracę!
            </div>
            <div style="font-size:12px;color:#64748b;">Jeżeli to była pomyłka, nadal możesz odnowić subskrypcję w Panelu przed wygaśnięciem terminu.</div>
          </div>
        `,
      }).catch(err => console.error('[cancel-subscription] Błąd wysyłki e-mail:', err));
    }



    return new Response(JSON.stringify({
      success: true,
      canceledAt: new Date(updatedSubscription.cancel_at! * 1000).toISOString(),
    }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    console.error('[cancel-subscription] Error:', err);
    return new Response(JSON.stringify({ error: 'Wystąpił nieoczekiwany błąd w API anulowania Stripe.' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
};
