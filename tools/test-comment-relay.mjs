/* Test of the comment relay Worker — worker/index.js and everything it calls.
 *
 * No wrangler, no workerd, no network. The Worker's entry point is an ordinary
 * ES module whose fetch() takes (Request, env, ctx), so it is driven directly
 * with fake bindings: a real CommentGate over a Map-backed storage, and a
 * global fetch that stands in for both api.anthropic.com and the tower. That
 * makes the interesting cases — the moderator returning 500, a comment that
 * tries to talk to the moderator, the tower refusing — reachable, which they
 * are not against the real thing.
 *
 *   node tools/test-comment-relay.mjs
 */
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const worker = (await import(join(ROOT, "worker/index.js"))).default;
const { CommentGate, decide, viewerKey } = await import(join(ROOT, "worker/gate.js"));
const { screen, format, escapeMarkdown, cleanName } = await import(join(ROOT, "worker/screen.js"));

const results = [];
const ok = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

/* ---------- fakes ---------- */
function fakeStorage() {
  const map = new Map();
  let alarm = null;
  return {
    map,
    async get(k) { return map.get(k); },
    async put(k, v) { map.set(k, v); },
    async delete(k) { (Array.isArray(k) ? k : [k]).forEach((x) => map.delete(x)); },
    async list({ prefix } = {}) {
      const out = new Map();
      for (const [k, v] of map) if (!prefix || k.startsWith(prefix)) out.set(k, v);
      return out;
    },
    async getAlarm() { return alarm; },
    async setAlarm(t) { alarm = t; },
  };
}

function makeEnv(overrides = {}) {
  const storage = fakeStorage();
  const env = {
    ASSETS: { fetch: async () => new Response("the site", { status: 200 }) },
    OWNCAST_TOKEN: "tower-token",
    ANTHROPIC_API_KEY: "sk-test",
    WATCH_HOST: "watch.example.test",
    MODERATION_PROVIDER: "anthropic",
    RELAY_BURST_SECONDS: "15",
    RELAY_VIEWER_PER_HOUR: "8",
    RELAY_CHANNEL_PER_HOUR: "200",
    ...overrides,
  };
  const gate = new CommentGate({ storage }, env);
  env.COMMENT_GATE = { idFromName: (n) => n, get: () => ({ fetch: (u, i) => gate.fetch(new Request(u, i)) }) };
  env.__storage = storage;
  env.__gate = gate;
  return env;
}

/* A fetch that answers for the moderator and the tower, and records both. */
let calls;
const realFetch = globalThis.fetch;
function installFetch({ verdict = { allow: true, category: "ok", note: "" }, moderatorStatus = 200,
                        moderatorBody = null, towerStatus = 200, moderatorThrows = false } = {}) {
  calls = { anthropic: [], tower: [] };
  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u.includes("anthropic")) {
      calls.anthropic.push({ url: u, init, body: JSON.parse(init.body) });
      if (moderatorThrows) throw new Error("connection reset");
      if (moderatorStatus !== 200) return new Response("nope", { status: moderatorStatus });
      const body = moderatorBody || {
        stop_reason: "tool_use",
        content: [{ type: "tool_use", name: "verdict", input: verdict }],
      };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (u.includes("watch.")) {
      calls.tower.push({ url: u, init, body: JSON.parse(init.body), auth: init.headers.Authorization });
      return new Response(towerStatus === 200 ? "ok" : "no", { status: towerStatus });
    }
    throw new Error("unexpected fetch to " + u);
  };
}

const post = (env, body, headers = {}) => worker.fetch(new Request("https://ch0.example/api/comment", {
  method: "POST",
  headers: { "Content-Type": "application/json", "CF-Connecting-IP": "203.0.113.7", ...headers },
  body: typeof body === "string" ? body : JSON.stringify(body),
}), env, {});
const read = async (res) => ({ status: res.status, json: await res.json().catch(() => null) });

/* ---------- 1. the pure pieces ---------- */
{
  const s = screen("hello there", "bob");
  ok("screen: an ordinary line passes", s.ok === true && s.body === "hello there", JSON.stringify(s));
  ok("screen: an empty line is refused", screen("   ", "b").reason === "empty");
  ok("screen: 281 characters is refused", screen("x".repeat(281), "b").reason === "too_long");
  ok("screen: four lines are refused", screen("a\nb\nc\nd", "b").reason === "too_many_lines");
  ok("screen: two links are refused", screen("https://a.test and https://b.test", "b").reason === "too_many_links");
  ok("screen: a wall of one character is refused", screen("a" + "b".repeat(30), "b").reason === "noise");
  ok("screen: shouting is refused", screen("THIS IS ALL OF IT IN CAPITALS FOREVER", "b").reason === "noise");
  ok("screen: mild profanity is NOT the filter's business",
     screen("what the hell is this film", "b").ok === true);

  /* The relay writes INTO the room, so markdown is an injection vector there
     the same way HTML was one on the page. */
  const img = format("x", "![](https://evil.test/tracker.png)");
  ok("escape: an image cannot be posted into the room", !/!\[\]\(/.test(img) && img.includes("\\!"), img);
  const link = format("x", "[free money](https://evil.test)");
  ok("escape: a markdown link cannot wear its own text", !/\[free money\]\(/.test(link), link);
  ok("escape: ordinary prose is left alone",
     format("bob", "great short, love the print").includes("great short, love the print"));
  /* Stripping the punctuation out of "<b>ad</b>" leaves its letters behind,
     which is harmless — what matters is that nothing markup-shaped survives,
     and that format() escapes the name a second time on the way out. */
  const messy = cleanName("<b>ad</b>*x*");
  ok("name: nothing markup-shaped survives a name", !/[<>*_`[\]()!~|#]/.test(messy), messy);
  ok("name: and the name is escaped again on the way into the room",
     !/\*\*bo\*b\*\*/.test(format(cleanName("bo*b"), "hi")), format(cleanName("bo*b"), "hi"));
  ok("name: an empty name gets a stand-in", cleanName("   ") === "someone");
  ok("name: a 40-character name is cut to 24", cleanName("z".repeat(40)).length === 24);
}

/* ---------- 2. the limiter, as arithmetic ---------- */
{
  const t = 1_000_000_000;
  ok("limiter: the first message is allowed", decide(t, [], []).ok === true);
  ok("limiter: a second message 5s later is not",
     decide(t, [t - 5000], []).reason === "too_fast");
  ok("limiter: 20s later it is", decide(t, [t - 20000], []).ok === true);
  const eight = Array.from({ length: 8 }, (_, i) => t - (i + 1) * 60_000);
  ok("limiter: the ninth message in an hour is refused", decide(t, eight, []).reason === "viewer_hour");
  ok("limiter: and it says when to come back", decide(t, eight, []).retryAfter > 3000);
  ok("limiter: an hour later the same viewer is fine",
     decide(t + 3_600_001, eight, []).ok === true);
  const flood = Array.from({ length: 200 }, (_, i) => t - i * 1000);
  ok("limiter: the channel ceiling stops the room", decide(t, [], flood).reason === "channel_hour");
  /* Order matters: one loud viewer must hit their OWN limit, not eat the
     room's allowance and lock everyone else out. */
  ok("limiter: a viewer's own limit is checked before the channel's",
     decide(t, [t - 1000], flood).reason === "too_fast");
  ok("key: the address is part of the key, so clearing an id does not reset it",
     viewerKey("a", "1.2.3.4") !== viewerKey("b", "1.2.3.4") &&
     viewerKey("a", "1.2.3.4").startsWith("1.2.3.4"));
}

/* ---------- 3. the Worker, end to end ---------- */
{
  installFetch();
  const env = makeEnv();

  const asset = await worker.fetch(new Request("https://ch0.example/"), env, {});
  ok("worker: anything that is not the relay is still the site", asset.status === 200 && (await asset.text()) === "the site");

  let r = await read(await worker.fetch(new Request("https://ch0.example/api/comment"), env, {}));
  ok("worker: GET reports the relay open and its limits",
     r.json.enabled === true && r.json.maxLength === 280 && r.json.cooldownSeconds === 15 && r.json.moderated === true,
     JSON.stringify(r.json));

  r = await read(await post(env, { body: "what is this short?", name: "bob", viewerId: "v1" }));
  ok("worker: an ordinary comment is accepted", r.status === 200 && r.json.ok === true, JSON.stringify(r.json));
  ok("worker: it reached the tower, once", calls.tower.length === 1, String(calls.tower.length));
  ok("worker: it went to the integrations endpoint with the bearer token",
     calls.tower[0].url === "https://watch.example.test/api/integrations/chat/send" &&
     calls.tower[0].auth === "Bearer tower-token", calls.tower[0].url);
  ok("worker: the room sees the sender's name and their words",
     calls.tower[0].body.body === "**bob** · what is this short?", calls.tower[0].body.body);

  /* The comment must reach the model as data inside a delimiter, and the
     system prompt must say so — this is the prompt-injection boundary. */
  const sent = calls.anthropic[0].body;
  ok("worker: the model is asked with a forced tool, not for prose",
     sent.tool_choice?.type === "tool" && sent.tool_choice?.name === "verdict" && sent.tools?.length === 1);
  ok("worker: the model is asked as haiku 4.5", sent.model === "claude-haiku-4-5", sent.model);
  ok("worker: the comment is wrapped as data, and the prompt says to treat it as data",
     sent.messages[0].content.includes("<comment>") && /NEVER as instructions/i.test(sent.system));
  ok("worker: the moderator is not asked for more tokens than a verdict needs",
     sent.max_tokens <= 200, String(sent.max_tokens));
}

/* ---------- 4. refusals ---------- */
{
  installFetch({ verdict: { allow: false, category: "advertising", note: "That reads as an advert." } });
  const env = makeEnv();
  const r = await read(await post(env, { body: "buy cheap watches at my site", name: "spammer", viewerId: "v2" }));
  ok("refuse: the model's no is honoured", r.status === 422 && r.json.reason === "refused", JSON.stringify(r.json));
  ok("refuse: the sender is told why, in the model's words", r.json.detail === "That reads as an advert.", r.json.detail);
  ok("refuse: nothing reached the room", calls.tower.length === 0, String(calls.tower.length));

  /* A refused comment must still have cost its sender an allowance, or a
     spammer gets unlimited free attempts at finding a phrasing that passes. */
  const again = await read(await post(env, { body: "something else entirely", name: "spammer", viewerId: "v2" }));
  ok("refuse: a refused comment still spends the allowance",
     again.status === 429 && again.json.reason === "too_fast", JSON.stringify(again.json));
}

/* ---------- 5. fail closed ---------- */
for (const [label, opts] of [
  ["the moderator returns 500", { moderatorStatus: 500 }],
  ["the moderator throws", { moderatorThrows: true }],
  ["the moderator answers with nonsense", { moderatorBody: { content: [{ type: "text", text: "sure, allow it" }] } }],
  ["the moderator refuses to answer", { moderatorBody: { stop_reason: "refusal", content: [] } }],
]) {
  installFetch(opts);
  const env = makeEnv();
  const r = await read(await post(env, { body: "hello", name: "bob", viewerId: "v3" }));
  const closed = r.status >= 400 && calls.tower.length === 0;
  ok(`closed: when ${label}, nothing is posted`, closed, `status=${r.status} tower=${calls.tower.length}`);
}
{
  installFetch({ moderatorStatus: 500 });
  const env = makeEnv();
  const r = await read(await post(env, { body: "hello", name: "bob", viewerId: "v4" }));
  ok("closed: a moderator outage reads as an outage, not a rejection",
     r.status === 503 && r.json.reason === "moderator_down", JSON.stringify(r.json));
}
{
  installFetch({ towerStatus: 500 });
  const env = makeEnv();
  const r = await read(await post(env, { body: "hello", name: "bob", viewerId: "v5" }));
  ok("closed: the tower refusing is reported as such", r.status === 502 && r.json.reason === "tower_refused", JSON.stringify(r.json));
}

/* ---------- 6. not configured ---------- */
{
  installFetch();
  const noToken = makeEnv({ OWNCAST_TOKEN: "" });
  let r = await read(await worker.fetch(new Request("https://ch0.example/api/comment"), noToken, {}));
  ok("unconfigured: with no tower token the relay reports itself closed", r.json.enabled === false);
  r = await read(await post(noToken, { body: "hi", name: "b", viewerId: "v6" }));
  ok("unconfigured: and refuses to take anything", r.status === 503 && r.json.reason === "unconfigured");

  const noModel = makeEnv({ ANTHROPIC_API_KEY: "" });
  r = await read(await worker.fetch(new Request("https://ch0.example/api/comment"), noModel, {}));
  ok("unconfigured: with no moderator the relay reports itself closed", r.json.enabled === false);
  r = await read(await post(noModel, { body: "hi", name: "b", viewerId: "v7" }));
  ok("unconfigured: a relay with no moderator takes nothing", r.status === 503, String(r.status));
  ok("unconfigured: and never called the tower", calls.tower.length === 0);

  const off = makeEnv({ MODERATION_PROVIDER: "off" });
  r = await read(await worker.fetch(new Request("https://ch0.example/api/comment"), off, {}));
  ok("unmoderated: provider=off is open but says it is not moderated",
     r.json.enabled === true && r.json.moderated === false, JSON.stringify(r.json));

  const disabled = makeEnv({ RELAY_ENABLED: "false" });
  r = await read(await post(disabled, { body: "hi", name: "b", viewerId: "v8" }));
  ok("switch: RELAY_ENABLED=false closes the relay without a site deploy",
     r.status === 503 && r.json.reason === "closed");
}

/* ---------- 7. bad callers ---------- */
{
  installFetch();
  const env = makeEnv();
  let r = await read(await post(env, { body: "hi", name: "b", viewerId: "v9" }, { Origin: "https://evil.test" }));
  ok("origin: another site cannot use the relay as a mouthpiece", r.status === 403, String(r.status));
  ok("origin: and nothing was posted", calls.tower.length === 0);

  r = await read(await post(env, { body: "hi", name: "b", viewerId: "v9" }, { Origin: "https://ch0.example" }));
  ok("origin: the station's own page can", r.status === 200, JSON.stringify(r.json));

  r = await read(await post(makeEnv(), "not json at all"));
  ok("input: a body that is not JSON is refused", r.status === 400 && r.json.reason === "bad_json");

  r = await read(await post(makeEnv(), "x".repeat(5000)));
  ok("input: a body over 4KB is refused before it is parsed", r.status === 413, String(r.status));

  const opts = await worker.fetch(new Request("https://ch0.example/api/comment", {
    method: "OPTIONS", headers: { Origin: "https://ch0.example" } }), env, {});
  ok("cors: preflight is answered for the station's own origin",
     opts.status === 204 && opts.headers.get("Access-Control-Allow-Origin") === "https://ch0.example");

  const del = await worker.fetch(new Request("https://ch0.example/api/comment", { method: "DELETE" }), env, {});
  ok("method: anything but GET/POST is refused", del.status === 405);
}

/* ---------- 8. the limiter, through the Worker ---------- */
{
  installFetch();
  const env = makeEnv();
  const send = (i) => post(env, { body: `message number ${i}`, name: "bob", viewerId: "vA" });

  let r = await read(await send(1));
  ok("rate: the first goes through", r.status === 200);
  r = await read(await send(2));
  ok("rate: the second, straight away, does not", r.status === 429 && r.json.reason === "too_fast", JSON.stringify(r.json));

  const res = await send(3);
  ok("rate: and it says how long to wait", Number(res.headers.get("Retry-After")) > 0, res.headers.get("Retry-After"));

  /* Walk the clock forward past the burst window eight times: the ninth is
     the hourly cap, not the burst one. */
  const realNow = Date.now;
  let t = realNow();
  Date.now = () => t;
  const env2 = makeEnv();
  const send2 = (i) => post(env2, { body: `line ${i}`, name: "bob", viewerId: "vB" });
  const codes = [];
  for (let i = 0; i < 9; i++) { t += 20_000; codes.push((await read(await send2(i))).status); }
  Date.now = realNow;
  ok("rate: eight an hour get through and the ninth does not",
     codes.slice(0, 8).every((c) => c === 200) && codes[8] === 429, codes.join(","));
}

/* ---------- 9. the object sweeps up after itself ---------- */
{
  const env = makeEnv();
  const st = env.__storage;
  await st.put("v:old|x", [Date.now() - 5 * 60 * 60 * 1000]);
  await st.put("v:new|y", [Date.now()]);
  await env.__gate.alarm();
  ok("sweep: an hours-dead viewer key is deleted", !st.map.has("v:old|x"));
  ok("sweep: a live one is kept", st.map.has("v:new|y"));
}

globalThis.fetch = realFetch;
const failed = results.filter((x) => !x.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) { console.log("\nFAILURES:"); failed.forEach((f) => console.log("  - " + f.name + (f.detail ? "  — " + f.detail : ""))); }
process.exit(failed.length ? 1 : 0);
