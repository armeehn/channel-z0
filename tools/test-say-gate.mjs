/* Real-browser test: the comment box appears only when the relay says it is open.
 *
 * initSay() gates the box with the `hidden` attribute and returns early when
 * GET /api/comment reports {enabled:false}. That logic was always right; what
 * failed was the CSS. `.chat-say { display: flex }` is an AUTHOR rule and the
 * UA stylesheet's `[hidden] { display: none }` is not, so the author rule won
 * and the form rendered with `hidden` still on it. A relay with no secrets —
 * which is exactly how it ships — showed a box nobody could post from.
 *
 * So this drives the real page against a stubbed /api/comment and asserts on
 * COMPUTED DISPLAY, not on the attribute. An assertion that reads
 * `el.hasAttribute("hidden")` passes on the bug.
 *
 *   node tools/test-say-gate.mjs
 */
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HOME = process.env.HOME || "";
const CHROME = process.env.CHROME ||
  `${HOME}/.cache/puppeteer/chrome/linux-150.0.7871.24/chrome-linux64/chrome`;
const ROOT = process.env.SITE_DIR || join(dirname(fileURLToPath(import.meta.url)), "..", "site");
const OUTDIR = process.env.OUTDIR || "/tmp/z0-say-gate-test";
const PORT = Number(process.env.PORT || 8793);

await mkdir(OUTDIR, { recursive: true });

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };
const server = createServer(async (req, res) => {
  let p = normalize(decodeURIComponent(req.url.split("?")[0]));
  if (p.endsWith("/")) p += "index.html";
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

const browser = await chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push("PAGEERROR: " + String(e)));

let relay = { enabled: false };
await page.route("**/api/comment*", (route) =>
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(relay) }));
// Keep the tower out of it; the chat backlog is not what is under test.
await page.route("**/api/chat**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
await page.route("**/hls/**", (route) => route.abort("failed"));

const shown = (id) => page.evaluate((i) => {
  const el = document.getElementById(i);
  if (!el) return { missing: true };
  const cs = getComputedStyle(el), b = el.getBoundingClientRect();
  return { display: cs.display, w: Math.round(b.width), h: Math.round(b.height),
           attr: el.hasAttribute("hidden") };
}, id);

// ── relay closed: no box ────────────────────────────────────────────────────
await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);
let s = await shown("chatSay");
ok("closed relay: the box is not rendered", s.display === "none", `display=${s.display} ${s.w}x${s.h}`);
ok("closed relay: it still carries the hidden attribute", s.attr === true);
ok("closed relay: the tower link stands",
   await page.evaluate(() => (document.getElementById("chatLink").textContent || "").trim().length > 0));
await page.screenshot({ path: join(OUTDIR, "closed.png") });

// ── every element the page hides with .hidden actually hides ────────────────
// One of six had an author display rule that beat [hidden]. Pin all six.
const audit = await page.evaluate(() => {
  const out = {};
  for (const id of ["chatSay", "chatJump", "chatNote", "chatUnread", "rail-chat", "rail-spec"]) {
    const el = document.getElementById(id);
    if (!el) { out[id] = "MISSING"; continue; }
    const had = el.hasAttribute("hidden");
    el.hidden = true;
    out[id] = getComputedStyle(el).display;
    el.hidden = had;
  }
  return out;
});
for (const [id, d] of Object.entries(audit)) {
  ok(`#${id} hides when hidden is set`, d === "none", `display=${d}`);
}

// ── relay open: the box appears ─────────────────────────────────────────────
relay = { enabled: true, maxLength: 280, cooldownSeconds: 15, perHour: 8, moderated: true };
await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);
s = await shown("chatSay");
ok("open relay: the box is rendered", s.display !== "none" && s.w > 0 && s.h > 0,
   `display=${s.display} ${s.w}x${s.h}`);
ok("open relay: the hidden attribute is gone", s.attr === false);
ok("open relay: the composer accepts the relay's max length",
   await page.evaluate(() => document.getElementById("chatInput").maxLength === 280));
await page.screenshot({ path: join(OUTDIR, "open.png") });

ok("no uncaught page errors", pageErrors.length === 0, pageErrors.join(" | ").slice(0, 200));

await browser.close();
server.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed; screenshots in ${OUTDIR}`);
process.exit(failed.length ? 1 : 0);
