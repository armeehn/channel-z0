/* Real-browser test of the comment box in SEC.01's rail.
 *
 * The relay itself is tested without a browser (tools/test-comment-relay.mjs).
 * This drives the other half: what the viewer sees when the relay says yes,
 * says no, says wait, or is not there at all. The test server stands in for
 * the Worker so every one of those answers is reachable on demand — against a
 * real relay only "yes" is easy to produce.
 *
 * Prerequisites (not vendored):
 *   PLAYWRIGHT  path to a playwright install
 *   CHROME      path to a full Chrome binary
 *
 *   node tools/test-chat-composer.mjs
 */
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HOME = process.env.HOME || "";
const PLAYWRIGHT = process.env.PLAYWRIGHT || `${HOME}/daily-bread/db-render/node_modules/playwright/index.mjs`;
const CHROME = process.env.CHROME || `${HOME}/.cache/puppeteer/chrome/linux-150.0.7871.24/chrome-linux64/chrome`;
const ROOT = process.env.SITE_DIR || join(dirname(fileURLToPath(import.meta.url)), "..", "site");
const OUTDIR = process.env.OUTDIR || "/tmp/z0-composer-test";
const PORT = Number(process.env.PORT || 8792);

const { chromium } = await import(PLAYWRIGHT);
await mkdir(OUTDIR, { recursive: true });

/* The stub relay. `relay` is rewritten between tests to make the Worker answer
   however this file needs it to. */
let relay = { status: 200, get: { enabled: true, maxLength: 280, cooldownSeconds: 5, perHour: 8, moderated: true },
              post: { status: 200, body: { ok: true }, headers: {} } };
const posted = [];

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };
const server = createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(req.url.split("?")[0]));
  if (path === "/api/comment") {
    if (req.method === "GET") {
      if (relay.status !== 200) { res.writeHead(relay.status).end("no relay"); return; }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(relay.get));
      return;
    }
    let raw = ""; for await (const c of req) raw += c;
    posted.push(JSON.parse(raw || "{}"));
    res.writeHead(relay.post.status, { "Content-Type": "application/json", ...relay.post.headers });
    res.end(JSON.stringify(relay.post.body));
    return;
  }
  let p = path; if (p.endsWith("/")) p += "index.html";
  try {
    const body = await readFile(join(ROOT, p));
    res.writeHead(200, { "Content-Type": TYPES[extname(p)] || "application/octet-stream" });
    res.end(body);
  } catch { res.writeHead(404).end("nope"); }
});
await new Promise((r) => server.listen(PORT, "127.0.0.1", r));

const results = [];
const ok = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

const browser = await chromium.launch({ executablePath: CHROME, args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"] });
const pageErrors = [];
let ctx, page;
async function open() {
  if (ctx) await ctx.close();
  ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  page = await ctx.newPage();
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  await page.waitForTimeout(1200);
}

const box = () => page.evaluate(() => {
  const f = document.getElementById("chatSay");
  const b = document.getElementById("chatSend");
  const r = b.getBoundingClientRect();
  return {
    shown: !f.hidden,
    name: document.getElementById("chatName").value,
    text: document.getElementById("chatInput").value,
    count: document.getElementById("chatCount").textContent,
    countLow: document.getElementById("chatCount").classList.contains("low"),
    note: document.getElementById("chatSayNote").textContent,
    noteBad: document.getElementById("chatSayNote").classList.contains("bad"),
    sendDisabled: b.disabled,
    sendLabel: b.innerText.trim(),
    sendBox: [Math.round(r.width * 100) / 100, Math.round(r.height * 100) / 100],
    link: document.getElementById("chatLink").textContent.trim(),
  };
});

/* ---------- 1. closed relays keep the box off the page ---------- */
relay = { ...relay, status: 404 };
await open();
let b = await box();
ok("closed: no Worker deployed (404) leaves the box hidden", b.shown === false);
ok("closed: and the tower link is still the way in", /SAY SOMETHING/.test(b.link), b.link);

relay = { status: 200, get: { enabled: false }, post: relay.post };
await open();
b = await box();
ok("closed: a relay that reports itself unconfigured leaves the box hidden", b.shown === false);

/* ---------- 2. open ---------- */
relay = { status: 200, get: { enabled: true, maxLength: 280, cooldownSeconds: 5, perHour: 8, moderated: true },
          post: { status: 200, body: { ok: true }, headers: {} } };
await open();
b = await box();
ok("open: the box appears when the relay says it is open", b.shown === true);
ok("open: the link stops claiming to be the only way in", /OPEN THE TOWER/.test(b.link), b.link);
ok("open: the name is prefilled with the one the tower gave this viewer", b.name.length > 0, b.name);
ok("open: SEND is dead until something is typed", b.sendDisabled === true);
ok("open: the counter starts at the relay's own limit", b.count === "280", b.count);

const emptyBox = (await box()).sendBox;
await page.fill("#chatInput", "what is this short?");
await page.waitForTimeout(120);
b = await box();
ok("typing: the counter counts down", b.count === String(280 - "what is this short?".length), b.count);
ok("typing: SEND wakes up", b.sendDisabled === false);
await page.fill("#chatInput", "x".repeat(270));
await page.waitForTimeout(120);
b = await box();
ok("typing: the counter goes red near the limit", b.countLow === true, b.count);
ok("typing: the textarea is capped at the relay's limit",
   (await page.inputValue("#chatInput")).length <= 280);

/* ---------- 3. sending ---------- */
await page.fill("#chatName", "test-viewer");
await page.fill("#chatInput", "lovely print on this one");
posted.length = 0;
/* The tower's room has a real backlog, so "empty" is not the assertion —
   "the send added nothing" is. Nothing is echoed optimistically: the message
   comes back down the websocket like everyone else's. */
const logBefore = await page.evaluate(() => document.querySelectorAll("#chatLog .chat-msg").length);
await page.click("#chatSend");
await page.waitForTimeout(500);
b = await box();
ok("send: the relay got the comment, the name and the viewer id",
   posted.length === 1 && posted[0].body === "lovely print on this one" && posted[0].name === "test-viewer" && typeof posted[0].viewerId === "string",
   JSON.stringify(posted[0]));
ok("send: the box is cleared on success", b.text === "");
ok("send: the viewer is told it went", /sent/i.test(b.note) && b.noteBad === false, b.note);
ok("send: nothing is echoed into the log — it comes back down the websocket",
   (await page.evaluate(() => document.querySelectorAll("#chatLog .chat-msg").length)) === logBefore,
   `log ${logBefore} -> ${await page.evaluate(() => document.querySelectorAll("#chatLog .chat-msg").length)}`);
ok("send: SEND is held for the relay's cooldown rather than failing", b.sendDisabled === true);
/* The whole point of this branch: a button that changes size while you use it. */
ok("send: SEND does not resize while sending", JSON.stringify(b.sendBox) === JSON.stringify(emptyBox),
   `${emptyBox} -> ${b.sendBox}`);

await page.reload({ waitUntil: "load" });
await page.waitForTimeout(1200);
ok("send: the name is remembered next time", (await box()).name === "test-viewer", (await box()).name);

/* ---------- 4. every way it can say no ---------- */
relay.post = { status: 422, body: { ok: false, reason: "refused", detail: "That reads as an advert." }, headers: {} };
await page.fill("#chatInput", "buy my watches");
await page.click("#chatSend");
await page.waitForTimeout(400);
b = await box();
ok("refused: the moderator's own sentence is shown", b.note === "That reads as an advert." && b.noteBad === true, b.note);
ok("refused: the words the viewer typed are NOT thrown away", b.text === "buy my watches", b.text);

relay.post = { status: 429, body: { ok: false, reason: "too_fast", detail: "One message every 15 seconds." }, headers: { "Retry-After": "3" } };
await page.fill("#chatInput", "again");
await page.click("#chatSend");
await page.waitForTimeout(400);
b = await box();
ok("rate limited: the viewer is told to wait", /every 15 seconds/.test(b.note) && b.noteBad === true, b.note);
ok("rate limited: SEND is held rather than firing at a relay that will refuse", b.sendDisabled === true);
await page.waitForTimeout(3600);
b = await box();
ok("rate limited: and it comes back by itself", b.sendDisabled === false);

relay.post = { status: 503, body: { ok: false, reason: "moderator_down", detail: "The moderator is offline, so nothing is being posted right now." }, headers: {} };
await page.fill("#chatInput", "hello");
await page.click("#chatSend");
await page.waitForTimeout(400);
b = await box();
ok("moderator down: said plainly, not as a rejection", /moderator is offline/i.test(b.note) && b.noteBad === true, b.note);
ok("moderator down: the text is kept", b.text === "hello");

/* ---------- 5. the keyboard ---------- */
relay.post = { status: 200, body: { ok: true }, headers: {} };
await open();
await page.fill("#chatInput", "typed and entered");
posted.length = 0;
await page.focus("#chatInput");
await page.keyboard.press("Enter");
await page.waitForTimeout(400);
ok("keyboard: Enter sends", posted.length === 1 && posted[0].body === "typed and entered", JSON.stringify(posted));
await page.waitForTimeout(5200);
await page.fill("#chatInput", "one");
await page.focus("#chatInput");
await page.keyboard.down("Shift"); await page.keyboard.press("Enter"); await page.keyboard.up("Shift");
await page.keyboard.type("two");
await page.waitForTimeout(200);
ok("keyboard: Shift+Enter is a new line, not a send",
   (await page.inputValue("#chatInput")).includes("\n") && posted.length === 1,
   JSON.stringify(await page.inputValue("#chatInput")));

/* ---------- 6. it does not cost the layout ---------- */
const fit = await page.evaluate(() => ({
  docScroll: document.documentElement.scrollHeight - document.documentElement.clientHeight,
  overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  panelOver: (() => { const p = document.getElementById("live"); return p.scrollHeight - p.clientHeight; })(),
  logH: Math.round(document.getElementById("chatLog").getBoundingClientRect().height),
  railW: Math.round(document.querySelector("#live .rail").getBoundingClientRect().width),
}));
ok("layout: the page still does not scroll with the box open", fit.docScroll <= 0 && fit.panelOver <= 0, JSON.stringify(fit));
ok("layout: no horizontal overflow", fit.overflowX <= 0, String(fit.overflowX));
ok("layout: the rail is still 292px", fit.railW === 292, String(fit.railW));
ok("layout: the chat log keeps a readable height alongside the box", fit.logH >= 150, `${fit.logH}px`);
await page.screenshot({ path: join(OUTDIR, "composer-1280.png") });

await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(300);
const narrow = await page.evaluate(() => ({
  overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  sendVisible: document.getElementById("chatSend").getBoundingClientRect().width > 0,
}));
ok("phone: no horizontal overflow at 390px", narrow.overflowX <= 0, String(narrow.overflowX));
ok("phone: SEND is reachable", narrow.sendVisible === true);
await page.screenshot({ path: join(OUTDIR, "composer-390.png"), fullPage: true });

ok("no uncaught JS errors", pageErrors.length === 0, pageErrors.slice(0, 3).join(" ; "));

const failed = results.filter((x) => !x.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) { console.log("\nFAILURES:"); failed.forEach((f) => console.log("  - " + f.name + (f.detail ? "  — " + f.detail : ""))); }
console.log(`screenshots: ${OUTDIR}`);
await browser.close();
server.close();
process.exit(failed.length ? 1 : 0);
