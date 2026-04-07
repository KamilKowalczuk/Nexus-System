import type { APIRoute } from 'astro';

export const prerender = false;

export const GET: APIRoute = async () => {
  try {
    const payloadUrl = import.meta.env.PAYLOAD_URL || 'http://127.0.0.1:3000';
    const res = await fetch(`${payloadUrl}/api/globals/landing-page?depth=0`, {
      headers: {
        'Content-Type': 'application/json',
      },
      // 3s timeout for slot check
      signal: AbortSignal.timeout(3000),
    });

    if (!res.ok) {
      console.warn('[API Slots] Payload not available, returning defaults');
      return new Response(JSON.stringify({ total: 10, used: 0, available: 10 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const data = await res.json();
    const totalSlots = data?.slots?.totalSlots ?? 10;
    const usedSlots = data?.slots?.usedSlots ?? 0;
    const available = Math.max(0, totalSlots - usedSlots);

    return new Response(JSON.stringify({ total: totalSlots, used: usedSlots, available }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
    });
  } catch (err: any) {
    console.error('[API Slots] Error:', err);
    // Fallback — nie blokuj strony jeśli Payload jest offline
    return new Response(JSON.stringify({ total: 10, used: 0, available: 10 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }
};
