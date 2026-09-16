/* ==========================================================================
   CHANNEL Z0 · the storefront Worker
   --------------------------------------------------------------------------
   Everything that is a file in site/ is still served as a static asset by
   Cloudflare, untouched — this Worker only exists for the paths that are not
   files. Today that is one: the moderated comment relay.

   Why a relay at all, when the page already reads the chat directly? Because
   reading needs no secret and writing does. A page that could post would have
   to carry a token that can post, and a token in a public page belongs to
   everyone who views it. So the page asks this Worker, which holds the token,
   applies the house rules, and speaks to Owncast itself.

   The order of the pipeline is the whole design:

     1. shape      (screen.js)  — free, and turns away most of it
     2. rate limit (gate.js)    — spends the viewer's allowance
     3. moderation (moderate.js)— the only step that costs money
     4. post       (owncast)    — the only step that is visible to the room

   Rate limiting comes BEFORE the model so a flood cannot run up a bill, and
   after the shape checks so obvious rubbish does not consume an allowance.
   ========================================================================== */
import { screen, format, LIMITS } from "./screen.js";
import { moderate } from "./moderate.js";
import { viewerKey, DEFAULT_LIMITS } from "./gate.js";
import { countReceivers, RECEIVER_WINDOW_S } from "./viewers.js";

export { CommentGate } from "./gate.js";

const RELAY_PATH = "/api/comment";
const RECEIVERS_PATH = "/api/viewers";

// How long the edge and browsers may reuse one receiver count. The analytics
// query behind it then runs a couple of times a minute no matter the audience.
const RECEIVERS_CACHE_S = 30;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === RELAY_PATH) {
      if (request.method === "OPTIONS") return preflight(request, env);
      if (request.method === "GET") return withCors(status(env), request, env);
      if (request.method === "POST") return withCors(await relay(request, env), request, env);
      return withCors(problem(405, "method_not_allowed", "POST a comment here."), request, env);
    }

    if (url.pathname === RECEIVERS_PATH) {
      if (request.method !== "GET") return withCors(problem(405, "method_not_allowed", "GET the receiver count here."), request, env);
      return withCors(await receivers(request, env, ctx), request, env);
    }

    // Everything else is the site. If the assets binding is missing (a
    // misconfigured wrangler.jsonc), say so instead of returning a blank 500.
    if (!env.ASSETS) return problem(500, "no_assets", "The static assets binding is not configured.");
    return env.ASSETS.fetch(request);
  },
};

/* ---- GET /api/viewers ----
 * Owncast stops seeing receivers once segments come from the CDN, so the
 * count comes from the CDN's analytics (worker/viewers.js). One answer is
 * cached at the edge for RECEIVERS_CACHE_S; a 503 with receivers:null means
 * "don't know", and the page falls back to whatever Owncast still reports. */
async function receivers(request, env, ctx) {
  const cache = globalThis.caches && globalThis.caches.default;
  const key = new Request(new URL(RECEIVERS_PATH, request.url).toString(), { method: "GET" });
  if (cache) {
    const hit = await cache.match(key);
    if (hit) return hit;
  }

  const n = await countReceivers(env);
  const known = n !== null;
  const res = json({ ok: known, receivers: n, window_s: RECEIVER_WINDOW_S }, known ? 200 : 503,
                   { "Cache-Control": `public, max-age=${RECEIVERS_CACHE_S}` });
  if (cache && known) ctx.waitUntil(cache.put(key, res.clone()));
  return res;
}

/* ---- GET /api/comment ----
   The page asks what it is allowed to render. A relay that is deployed but
   not configured must report itself CLOSED rather than showing a comment box
   that can only fail — the storefront falls back to linking the tower. */
function status(env) {
  const configured = Boolean(env.OWNCAST_TOKEN) && moderatorConfigured(env);
  return json({
    enabled: configured && env.RELAY_ENABLED !== "false",
    maxLength: LIMITS.maxLength,
    cooldownSeconds: Number(env.RELAY_BURST_SECONDS) || DEFAULT_LIMITS.burstSeconds,
    perHour: Number(env.RELAY_VIEWER_PER_HOUR) || DEFAULT_LIMITS.viewerPerHour,
    moderated: (env.MODERATION_PROVIDER || "anthropic").toLowerCase() !== "off",
  });
}

function moderatorConfigured(env) {
  const p = (env.MODERATION_PROVIDER || "anthropic").toLowerCase();
  if (p === "off") return true;
  if (p === "workers-ai") return Boolean(env.AI);
  return Boolean(env.ANTHROPIC_API_KEY);
}

/* ---- POST /api/comment ---- */
async function relay(request, env) {
  if (!sameOrigin(request, env)) {
    return problem(403, "bad_origin", "This relay only takes comments from the station's own page.");
  }
  if (env.RELAY_ENABLED === "false") {
    return problem(503, "closed", "The comment relay is closed.");
  }
  if (!env.OWNCAST_TOKEN) {
    return problem(503, "unconfigured", "The relay has no way to reach the tower yet.");
  }
  if (!moderatorConfigured(env)) {
    return problem(503, "unconfigured", "The relay has no moderator, so it is not taking comments.");
  }

  // Read with a hard ceiling: never hand an unbounded body to JSON.parse.
  const raw = await readCapped(request, 4096);
  if (raw === null) return problem(413, "too_big", "That is far too much text.");
  let payload;
  try { payload = JSON.parse(raw); } catch { return problem(400, "bad_json", "That did not arrive as JSON."); }

  // 1. shape
  const shaped = screen(payload.body, payload.name);
  if (!shaped.ok) return problem(422, shaped.reason, shaped.detail);

  // 2. allowance — check and spend in one trip, or two senders race it
  const ip = request.headers.get("CF-Connecting-IP") || "0.0.0.0";
  const key = viewerKey(payload.viewerId, ip);
  const gate = env.COMMENT_GATE.get(env.COMMENT_GATE.idFromName("channel"));
  const spend = await gate.fetch("https://gate/take", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  }).then((r) => r.json());
  if (!spend.ok) {
    return problem(429, spend.reason, spend.detail, { "Retry-After": String(spend.retryAfter || 30) });
  }

  // 3. the model
  const verdict = await moderate(env, shaped.body);
  if (!verdict.allow) {
    const down = verdict.category === "moderator_down";
    return problem(down ? 503 : 422, down ? "moderator_down" : "refused",
      down ? "The moderator is offline, so nothing is being posted right now." : (verdict.note || "That one did not pass the house rules."),
      {}, { category: verdict.category });
  }

  // 4. the room
  const posted = await postToTower(env, format(shaped.name, shaped.body));
  if (!posted.ok) return problem(502, "tower_refused", "The tower would not take it.", {}, { detail: posted.detail });

  return json({ ok: true });
}

async function postToTower(env, body) {
  // OWNCAST_BASE wins when it is set. `wrangler dev` against the real host
  // would post into the live room on the first test keystroke, so local runs
  // point this at a stub — and it is the only way to do that.
  const base = env.OWNCAST_BASE || `https://${env.WATCH_HOST}`;
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/api/integrations/chat/send`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${env.OWNCAST_TOKEN}`,
      },
      body: JSON.stringify({ body }),
    });
    if (!res.ok) return { ok: false, detail: `owncast ${res.status}` };
    return { ok: true };
  } catch (e) {
    return { ok: false, detail: String(e && e.message || e).slice(0, 120) };
  }
}

/* ---- plumbing ---- */

/** Same-origin only. The page and the relay share an origin by construction,
    so anything else is someone else's page using this relay as a mouthpiece. */
function sameOrigin(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin) return true;            // same-origin fetches may omit it
  const allowed = allowedOrigins(request, env);
  return allowed.includes(origin);
}
function allowedOrigins(request, env) {
  const self = new URL(request.url).origin;
  const extra = String(env.RELAY_ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
  return [self, ...extra];
}
function corsHeaders(request, env) {
  const origin = request.headers.get("Origin");
  if (origin && allowedOrigins(request, env).includes(origin)) {
    return { "Access-Control-Allow-Origin": origin, "Vary": "Origin" };
  }
  return {};
}
function withCors(response, request, env) {
  const out = new Response(response.body, response);
  for (const [k, v] of Object.entries(corsHeaders(request, env))) out.headers.set(k, v);
  return out;
}
function preflight(request, env) {
  return new Response(null, {
    status: 204,
    headers: {
      ...corsHeaders(request, env),
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    },
  });
}

/** Read at most `limit` bytes, or give up. Guards against a body that is
    streamed forever by a client that never closes it. */
async function readCapped(request, limit) {
  const reader = request.body?.getReader();
  if (!reader) return "";
  const chunks = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) { try { await reader.cancel(); } catch {} return null; }
    chunks.push(value);
  }
  const merged = new Uint8Array(size);
  let at = 0;
  for (const c of chunks) { merged.set(c, at); at += c.byteLength; }
  return new TextDecoder().decode(merged);
}

function json(obj, status = 200, headers = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });
}
function problem(status, reason, detail, headers = {}, extra = {}) {
  return json({ ok: false, reason, detail, ...extra }, status, headers);
}
