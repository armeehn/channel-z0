/* ==========================================================================
   CHANNEL Z0 · comment relay — the rate limiter
   --------------------------------------------------------------------------
   Three limits, and they answer three different questions:

     burst    — "is one person hammering the button?"      (per viewer, seconds)
     sustained— "is one person here all night?"            (per viewer, an hour)
     channel  — "is the whole room, or a botnet, running   (everyone, an hour)
                 up the moderation bill?"

   The channel limit is the one that matters financially: every comment that
   gets past the cheap checks costs a model call, and without a ceiling a
   single afternoon of attention can spend real money. It is deliberately
   checked LAST so that a flood from one viewer is turned away by their own
   limit first and does not eat the room's allowance.

   A Durable Object rather than KV: rate limiting is read-modify-write and KV
   is eventually consistent, so a KV limiter is a limiter that can be beaten by
   sending faster. One object serialises every decision for the channel, which
   is the right shape for a station with a handful of viewers and would be the
   wrong shape for a million.
   ========================================================================== */

export const DEFAULT_LIMITS = {
  burstSeconds: 15,        // one comment per viewer per 15s
  viewerPerHour: 8,
  channelPerHour: 200,
};

/* ---- the decision, as a pure function ----
   Kept separate from the Durable Object so it can be tested without any
   Cloudflare runtime at all: hand it a clock and two arrays of timestamps. */
export function decide(now, viewerHits, channelHits, limits = DEFAULT_LIMITS) {
  const hour = 60 * 60 * 1000;
  const recentViewer = viewerHits.filter((t) => now - t < hour);
  const recentChannel = channelHits.filter((t) => now - t < hour);

  const last = recentViewer.length ? Math.max(...recentViewer) : -Infinity;
  const sinceLast = now - last;
  const burstMs = limits.burstSeconds * 1000;
  if (sinceLast < burstMs) {
    return {
      ok: false, reason: "too_fast",
      retryAfter: Math.ceil((burstMs - sinceLast) / 1000),
      detail: `One message every ${limits.burstSeconds} seconds.`,
      recentViewer, recentChannel,
    };
  }
  if (recentViewer.length >= limits.viewerPerHour) {
    const oldest = Math.min(...recentViewer);
    return {
      ok: false, reason: "viewer_hour",
      retryAfter: Math.ceil((hour - (now - oldest)) / 1000),
      detail: `${limits.viewerPerHour} messages an hour each. Watch for a bit.`,
      recentViewer, recentChannel,
    };
  }
  if (recentChannel.length >= limits.channelPerHour) {
    const oldest = Math.min(...recentChannel);
    return {
      ok: false, reason: "channel_hour",
      retryAfter: Math.ceil((hour - (now - oldest)) / 1000),
      detail: "The room is at its limit for this hour.",
      recentViewer, recentChannel,
    };
  }
  return { ok: true, recentViewer, recentChannel };
}

/** Key a viewer by BOTH their id and their address: clearing localStorage
    makes a new id, and a shared address is the thing that cannot be reset. */
export function viewerKey(viewerId, ip) {
  const id = String(viewerId || "").replace(/[^\w.-]/g, "").slice(0, 40);
  const addr = String(ip || "").slice(0, 45);
  return `${addr}|${id}`;
}

export class CommentGate {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.limits = {
      burstSeconds: num(env.RELAY_BURST_SECONDS, DEFAULT_LIMITS.burstSeconds),
      viewerPerHour: num(env.RELAY_VIEWER_PER_HOUR, DEFAULT_LIMITS.viewerPerHour),
      channelPerHour: num(env.RELAY_CHANNEL_PER_HOUR, DEFAULT_LIMITS.channelPerHour),
    };
  }

  async fetch(request) {
    const url = new URL(request.url);
    const now = Date.now();

    if (url.pathname === "/peek") {
      const key = url.searchParams.get("key") || "";
      const viewerHits = (await this.state.storage.get("v:" + key)) || [];
      const channelHits = (await this.state.storage.get("channel")) || [];
      return json(decide(now, viewerHits, channelHits, this.limits));
    }

    // /take: check and, if allowed, SPEND the allowance in the same trip.
    // Two round trips (ask, then spend) is a race, and the race is the bug.
    const { key } = await request.json();
    const vKey = "v:" + key;
    const viewerHits = (await this.state.storage.get(vKey)) || [];
    const channelHits = (await this.state.storage.get("channel")) || [];
    const verdict = decide(now, viewerHits, channelHits, this.limits);

    if (verdict.ok) {
      await this.state.storage.put(vKey, [...verdict.recentViewer, now]);
      await this.state.storage.put("channel", [...verdict.recentChannel, now]);
      // Sweep abandoned viewer keys once a day; without it every address that
      // ever commented stays in storage forever.
      if (!(await this.state.storage.getAlarm())) {
        await this.state.storage.setAlarm(now + 24 * 60 * 60 * 1000);
      }
    }
    return json({ ok: verdict.ok, reason: verdict.reason, retryAfter: verdict.retryAfter, detail: verdict.detail });
  }

  async alarm() {
    const cutoff = Date.now() - 60 * 60 * 1000;
    const all = await this.state.storage.list({ prefix: "v:" });
    const dead = [];
    for (const [k, hits] of all) {
      if (!Array.isArray(hits) || !hits.some((t) => t > cutoff)) dead.push(k);
    }
    if (dead.length) await this.state.storage.delete(dead);
  }
}

function num(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
}
