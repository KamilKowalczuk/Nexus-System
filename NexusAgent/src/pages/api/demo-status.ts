import type { APIRoute } from 'astro';

export const prerender = false;

const PAYLOAD_URL = import.meta.env.PAYLOAD_URL || process.env.PAYLOAD_URL || 'http://localhost:3000';
const PAYLOAD_API_KEY = import.meta.env.PAYLOAD_API_KEY || process.env.PAYLOAD_API_KEY || '';

export const GET: APIRoute = async ({ clientAddress }) => {
  try {
    // Extract IP address (secure — provided by Astro adapter, not spoofable)
    const ip = clientAddress || '127.0.0.1';
    
    // Query Payload CMS for this IP
    const response = await fetch(`${PAYLOAD_URL}/api/demo-limits?where[ipAddress][equals]=${encodeURIComponent(String(ip))}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    });

    if (!response.ok) {
      console.error('[API Demo Status] Failed to fetch from Payload:', await response.text());
      return new Response(JSON.stringify({ usageCount: 0, maxUsage: 4, isLocked: false }), { status: 200 });
    }

    const data = await response.json();
    const doc = data.docs && data.docs.length > 0 ? data.docs[0] : null;
    
    const usageCount = doc ? doc.usageCount : 0;
    const maxUsage = 4;
    const isLocked = doc?.isBlocked || usageCount >= maxUsage;

    return new Response(JSON.stringify({ usageCount, maxUsage, isLocked }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json'
      }
    });
  } catch (err: any) {
    console.error('[API Demo Status] Error:', err);
    return new Response(JSON.stringify({ error: err.message }), { status: 500 });
  }
};
