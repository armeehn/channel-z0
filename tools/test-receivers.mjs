/* Receiver count: GET /api/viewers asks the CDN's analytics who pulled the
 * playlist lately. No network: the GraphQL API is faked.
 *   node tools/test-receivers.mjs
 */
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const worker = (await import(join(ROOT, "worker/index.js"))).default;
const { countReceivers, RECEIVER_WINDOW_S } = await import(join(ROOT, "worker/viewers.js"));

const results = [];
const ok = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

const ORIGIN = "https://ch0.example";
const ZONE = "0123456789abcdef0123456789abcdef";

function makeEnv(overrides = {}) {
  return {
    ASSETS: { fetch: async () => new Response("the site", { status: 200 }) },
    CF_ANALYTICS_TOKEN: "test-token",
    ANALYTICS_ZONE_TAG: ZONE,
    HLS_HOST: "hls.ch0.example",
    ...overrides,
  };
}

const ctx = { waitUntil: () => {} };

/* A fetch that plays the GraphQL API and records what it was asked. */
const realFetch = globalThis.fetch;
const seen = [];
function installFetch({ ips = 3, status = 200, body = null } = {}) {
  globalThis.fetch = async (url, init) => {
    seen.push({ url: String(url), init });
    const groups = Array.from({ length: ips }, (_, i) => ({ dimensions: { clientIP: `10.0.0.${i}` } }));
    const payload = body ?? { data: { viewer: { zones: [{ httpRequestsAdaptiveGroups: groups }] } }, errors: null };
    return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
  };
}

const get = (env, path = "/api/viewers", init = {}) => worker.fetch(new Request(ORIGIN + path, init), env, ctx);

/* ---------- 1. the count is the number of distinct IPs ---------- */
installFetch({ ips: 7 });
{
  const r = await get(makeEnv());
  const j = await r.json();
  ok("counts distinct IPs pulling the playlist", r.status === 200 && j.ok === true && j.receivers === 7, JSON.stringify(j));
  ok("answer carries the window", j.window_s === RECEIVER_WINDOW_S, String(j.window_s));
  ok("answer is cacheable at the edge", /max-age=\d+/.test(r.headers.get("Cache-Control") || ""), r.headers.get("Cache-Control"));

  const q = JSON.parse(seen.at(-1).init.body).query;
  ok("query is scoped to the HLS host and the variant playlist",
     q.includes('clientRequestHTTPHost: "hls.ch0.example"') && q.includes('clientRequestPath: "/hls/0/stream.m3u8"'));
  ok("query carries the bearer token", (seen.at(-1).init.headers.Authorization || "") === "Bearer test-token");
}

/* ---------- 2. zero is a real answer ---------- */
installFetch({ ips: 0 });
{
  const j = await (await get(makeEnv())).json();
  ok("nobody tuned in reads as 0, not as an error", j.ok === true && j.receivers === 0, JSON.stringify(j));
}

/* ---------- 3. not configured: honest 503, no network call ---------- */
seen.length = 0;
installFetch({ ips: 5 });
{
  const r = await get(makeEnv({ CF_ANALYTICS_TOKEN: "" }));
  const j = await r.json();
  ok("missing token answers 503 with receivers null", r.status === 503 && j.ok === false && j.receivers === null, JSON.stringify(j));
  ok("missing token never calls the API", seen.length === 0, String(seen.length));
}

/* ---------- 4. API trouble degrades to null, never throws ---------- */
installFetch({ status: 500 });
ok("HTTP 500 from the API reads as null", (await countReceivers(makeEnv())) === null);
installFetch({ body: { data: null, errors: [{ message: "unknown field" }] } });
ok("GraphQL error reads as null", (await countReceivers(makeEnv())) === null);
globalThis.fetch = async () => { throw new Error("boom"); };
ok("network failure reads as null", (await countReceivers(makeEnv())) === null);

/* ---------- 5. only GET ---------- */
installFetch({ ips: 1 });
{
  const r = await get(makeEnv(), "/api/viewers", { method: "POST" });
  ok("POST is refused", r.status === 405, String(r.status));
}

/* ---------- 6. the site is untouched ---------- */
{
  const r = await get(makeEnv(), "/");
  ok("other paths still fall through to the site", r.status === 200 && (await r.text()) === "the site");
}

globalThis.fetch = realFetch;

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
