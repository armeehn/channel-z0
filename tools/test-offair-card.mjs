/* Real-browser test of the storefront's OFF AIR card.
 *
 * The card is the loudest thing on the page, and it used to be driven only by
 * the player: it shipped with .show in the markup and came off only when
 * somebody pressed TUNE IN. So a viewer landing on a channel that WAS
 * broadcasting read "OFF AIR" across the picture while the chip beside it said
 * ON AIR. What this pins is that the card reports the STATION.
 *
 * The tower is stubbed (page.route over /api/status) so every case here is
 * deterministic and the suite passes with the real tower up, down or gone. One
 * optional section at the end tunes in against the live tower if it answers.
 *
 * Prerequisites, neither of which this repo vendors:
 *   PLAYWRIGHT  path to a playwright install   (default: $HOME/daily-bread/db-render/node_modules/playwright/index.mjs)
 *   CHROME      path to a full Chrome binary   (default: the puppeteer cache below)
 *
 *   node tools/test-offair-card.mjs
 *
 * Screenshots land in $OUTDIR (default /tmp/z0-offair-test).
 */
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HOME = process.env.HOME || "";
const PLAYWRIGHT = process.env.PLAYWRIGHT || `${HOME}/daily-bread/db-render/node_modules/playwright/index.mjs`;
const CHROME = process.env.CHROME ||
  `${HOME}/.cache/puppeteer/chrome/linux-150.0.7871.24/chrome-linux64/chrome`;
const ROOT = process.env.SITE_DIR || join(dirname(fileURLToPath(import.meta.url)), "..", "site");
const OUTDIR = process.env.OUTDIR || "/tmp/z0-offair-test";
const PORT = Number(process.env.PORT || 8791);

const { chromium } = await import(PLAYWRIGHT);
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

const browser = await chromium.launch({
  executablePath: CHROME,
  args: ["--autoplay-policy=no-user-gesture-required", "--no-sandbox"],
});
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push("PAGEERROR: " + String(e)));
// Resource 404s are NOT this feature's business and one of them is a known
// pre-existing fault: the pinned cdnjs hls.js build returns 404 and the
// jsdelivr fallback quietly covers it. Chrome also 404s /favicon.ico against
// the throwaway static server. Count script errors, not fetch failures.
page.on("console", (m) => {
  if (m.type() !== "error") return;
  const t = m.text();
  if (/Failed to load resource/i.test(t)) return;
  pageErrors.push(t);
});

/* The tower, as this test tells it. `tower` is re-pointed between cases and the
   route reads it at request time, so one handler serves every scenario. */
let tower = { online: true, streamTitle: "CH0 · A TEST TRANSMISSION", viewerCount: 3 };
await page.route("**/api/status*", async (route) => {
  if (tower === "unreachable") return route.abort("failed");
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ...tower, serverTime: new Date().toISOString(), versionNumber: "0.2.5" }),
  });
});
// Nothing here needs the real stream; keep the tower's bytes out of the test.
await page.route("**/hls/**", (route) => route.abort("failed"));

const card = () => page.evaluate(() => ({
  shown: document.getElementById("offair").classList.contains("show"),
  tag: document.getElementById("offairTag").textContent.trim(),
  sub: document.getElementById("offairSub").textContent.trim(),
  chipOn: document.getElementById("airChip").classList.contains("on"),
}));
const poll = async () => { await page.evaluate(() => pollStatus()); await page.waitForTimeout(150); };

await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1200);

// ── the bug: a live channel, nobody tuned in ────────────────────────────────
let c = await card();
ok("card is up before anyone tunes in", c.shown);
ok("a live channel does not read OFF AIR", c.tag === "ON AIR", `tag="${c.tag}"`);
ok("it says how to watch instead", /TUNE IN/.test(c.sub), `sub="${c.sub}"`);
ok("chip and card agree", c.chipOn === (c.tag === "ON AIR"), `chip=${c.chipOn} tag="${c.tag}"`);
await page.screenshot({ path: join(OUTDIR, "live-untuned.png") });

// ── the tower says the channel is down ─────────────────────────────────────
tower = { online: false, viewerCount: 0 };
await poll();
c = await card();
ok("a channel that is down reads OFF AIR", c.tag === "OFF AIR", `tag="${c.tag}"`);
ok("with the sign-off line", /RESUMES SHORTLY/.test(c.sub), `sub="${c.sub}"`);
ok("chip and card agree off air", c.chipOn === false && c.tag === "OFF AIR");
await page.screenshot({ path: join(OUTDIR, "genuinely-off.png") });

// ── it comes back ───────────────────────────────────────────────────────────
tower = { online: true, streamTitle: "CH0 · BACK ON", viewerCount: 1 };
await poll();
c = await card();
ok("sign-on repaints the card without a reload", c.tag === "ON AIR", `tag="${c.tag}"`);

// ── a tower we cannot reach claims nothing ─────────────────────────────────
tower = "unreachable";
await poll();
c = await card();
ok("an unreachable tower is not a broadcast", c.tag === "OFF AIR", `tag="${c.tag}"`);
ok("receiver count goes to —",
   await page.evaluate(() => document.getElementById("viewerNote").textContent.includes("—")));

// ── a receiver that cannot decode keeps its own message ────────────────────
// The old code wrote that sentence into the card by hand, so the next tower
// poll painted over it. It has to survive one.
tower = { online: true, streamTitle: "CH0 · STILL GOING", viewerCount: 2 };
await page.evaluate(() => { state.receiverDead = true; showOffair(true); });
await poll();
c = await card();
ok("a dead receiver still says so after a poll", /CANNOT DECODE/.test(c.sub), `sub="${c.sub}"`);
ok("and does not claim the station is off", c.tag === "OFF AIR", `tag="${c.tag}"`);
await page.evaluate(() => { state.receiverDead = false; });

// ── a stalled player blames the receiver, not the station ──────────────────
await poll();
await page.evaluate(() => { state.tuned = true; showOffair(true); });
c = await card();
ok("a stall on a live channel does not read OFF AIR", c.tag === "ON AIR", `tag="${c.tag}"`);
ok("it says it is looking", /SEEKING SIGNAL/.test(c.sub), `sub="${c.sub}"`);
await page.evaluate(() => { state.tuned = false; });

// ── the card is not left over the PeerTube iframe ──────────────────────────
// That backend replaces the whole screen frame, card and all, so the card
// cannot be stranded over the iframe. Pinned because the obvious "fix" is to
// hide the card there, and hiding a node that no longer exists is a no-op
// that reads like a guarantee.
const embedLeft = await page.evaluate(() => {
  usePeerTubeEmbed("about:blank");
  return { card: !!document.getElementById("offair"), iframe: !!document.querySelector(".screen-frame iframe") };
});
ok("PeerTube embed puts its own player on the screen", embedLeft.iframe);
ok("and leaves no card behind to cover it", embedLeft.card === false);

// ── with the real tower, if it answers: tuning in clears the card ──────────
await page.unroute("**/hls/**");
await page.unroute("**/api/status*");
await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1500);
await page.click("#tuneBtn").catch(() => {});
const playing = await page.waitForFunction(
  () => { const v = document.getElementById("tv"); return v && v.readyState >= 2 && !v.paused; },
  { timeout: 20000 }).then(() => true).catch(() => false);
if (playing) {
  await page.waitForTimeout(600);
  c = await card();
  ok("a playing picture has no card over it", c.shown === false, `shown=${c.shown}`);
  ok("and the chip is lit", c.chipOn === true);
  await page.screenshot({ path: join(OUTDIR, "tuned-in.png") });
} else {
  console.log("SKIP  live tune-in — the tower did not answer");
}

// ── the new wording fits the small screen ──────────────────────────────────
// "ON AIR" is a character shorter than "OFF AIR", so the slab only ever
// shrinks — but the sub line is longer than the one it replaced.
await page.setViewportSize({ width: 390, height: 780 });
await page.evaluate(() => { state.owncastOnline = true; state.tuned = false; showOffair(true); });
await page.waitForTimeout(300);
const fits = await page.evaluate(() => {
  const f = document.querySelector(".screen-frame").getBoundingClientRect();
  const inside = (id) => {
    const r = document.getElementById(id).getBoundingClientRect();
    return r.left >= f.left - 1 && r.right <= f.right + 1;
  };
  return { tag: inside("offairTag"), sub: inside("offairSub"),
           overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
});
ok("card stays inside the frame at 390px", fits.tag && fits.sub);
ok("no horizontal overflow at 390px", fits.overflow <= 0, `overflow=${fits.overflow}px`);
await page.screenshot({ path: join(OUTDIR, "mobile.png") });

ok("no uncaught page errors", pageErrors.length === 0, pageErrors.join(" | ").slice(0, 200));

await browser.close();
server.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed; screenshots in ${OUTDIR}`);
process.exit(failed.length ? 1 : 0);
