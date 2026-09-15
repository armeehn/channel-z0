/* Real-browser test of the storefront's on-picture NOW SHOWING plate.
 *
 * Serves site/ over http and drives it with Playwright, the same way
 * tools/test-player-controls.mjs does. It needs the tower to be ON AIR for the
 * "shows the live title" assertion; everything else passes off air.
 *
 * Prerequisites: playwright-core (npm ci), and
 *   CHROME      path to a full Chrome binary   (default: the puppeteer cache below)
 *
 *   node tools/test-now-plate.mjs
 *
 * Screenshots land in $OUTDIR (default /tmp/z0-now-plate-test).
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
const OUTDIR = process.env.OUTDIR || "/tmp/z0-now-plate-test";
const PORT = Number(process.env.PORT || 8789);

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

await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1500);

// Tune in first. The plate is furniture painted over a PICTURE, and with the
// OFF AIR bars up it is deliberately covered — testing it against the off-air
// screen would prove nothing and the screenshots would show nothing.
await page.click("#tuneBtn").catch(() => {});
const playing = await page.waitForFunction(
  () => { const v = document.getElementById("tv"); return v && v.readyState >= 2 && !v.paused; },
  { timeout: 20000 }).then(() => true).catch(() => false);
ok("stream is playing (the plate is tested over a picture)", playing,
   playing ? "" : "tower unreachable — the rest still runs, over OFF AIR bars");
await page.waitForTimeout(800);

// ── the plate exists and is out of the way until asked for ──────────────────
const plate = page.locator("#nowPlate");
ok("plate is in the DOM", await plate.count() === 1);

const style = await plate.evaluate((el) => {
  const cs = getComputedStyle(el);
  return { opacity: cs.opacity, pointerEvents: cs.pointerEvents, zIndex: cs.zIndex,
           position: cs.position };
});
ok("hidden until hovered", style.opacity === "0", `opacity=${style.opacity}`);
ok("never eats a click", style.pointerEvents === "none", `pointer-events=${style.pointerEvents}`);
ok("positioned over the picture", style.position === "absolute");

const offairZ = await page.locator("#offair").evaluate((el) => getComputedStyle(el).zIndex);
ok("OFF AIR bars cover the plate", Number(offairZ) > Number(style.zIndex),
   `offair z=${offairZ} plate z=${style.zIndex}`);

// ── hover reveals it ────────────────────────────────────────────────────────
await page.hover(".screen-frame");
await page.waitForTimeout(400);
const hovered = await plate.evaluate((el) => getComputedStyle(el).opacity);
ok("hover reveals the plate", hovered === "1", `opacity=${hovered}`);
await page.screenshot({ path: join(OUTDIR, "hover.png") });

// ── it says the same thing the FEED row says ────────────────────────────────
await page.waitForTimeout(2500);   // let the first tower poll land
const titles = await page.evaluate(() => ({
  feed: document.getElementById("nowShowing").textContent.trim(),
  plate: document.getElementById("nowPlateTitle").textContent.trim(),
}));
const stripped = titles.feed.replace(/^\s*CH0\s*·\s*/i, "");
ok("plate agrees with the FEED row", titles.plate === stripped,
   `feed="${titles.feed}" plate="${titles.plate}"`);
ok("plate carries a real title", titles.plate.length > 1 && titles.plate !== "—",
   `"${titles.plate}"`);
ok("channel prefix is not stuttered", !/^CH0\s*·/i.test(titles.plate));

// ── it tracks the schedule/tower rather than being painted once ─────────────
const tracks = await page.evaluate(async () => {
  const before = document.getElementById("nowPlateTitle").textContent;
  state.streamTitle = "CH0 · A TEST TRANSMISSION";
  updateNowShowing();
  const after = document.getElementById("nowPlateTitle").textContent;
  return { before, after };
});
ok("updates when the tower's title changes", tracks.after === "A TEST TRANSMISSION",
   `"${tracks.before}" -> "${tracks.after}"`);

// ── moving off the picture puts it away again ───────────────────────────────
await page.mouse.move(5, 5);
await page.waitForTimeout(400);
ok("hides again when the pointer leaves",
   await plate.evaluate((el) => getComputedStyle(el).opacity) === "0");

// ── the plate does not block the transport underneath it ────────────────────
const hitsVideo = await page.evaluate(() => {
  const p = document.getElementById("nowPlate").getBoundingClientRect();
  const el = document.elementFromPoint(p.left + p.width / 2, p.top + p.height / 2);
  return el ? el.id || el.tagName : "none";
});
ok("a click through the plate reaches the picture", hitsVideo !== "nowPlate",
   `elementFromPoint -> ${hitsVideo}`);

// ── full screen: it comes up with the frame, and fades with the transport ───
await page.click("#fsBtn");
await page.waitForFunction(() => document.fullscreenElement !== null, { timeout: 5000 })
  .catch(() => {});
const inFs = await page.evaluate(() => {
  const fe = document.fullscreenElement;
  return !!fe && fe.contains(document.getElementById("nowPlate"));
});
ok("plate is inside the full-screen element", inFs);
await page.hover(".screen-frame");
await page.waitForTimeout(300);
await page.screenshot({ path: join(OUTDIR, "fullscreen.png") });
// Read AFTER the .16s fade, not during it: getComputedStyle mid-transition
// returns the value the animation is currently on, which is still 1.
await page.evaluate(() => document.querySelector(".screen-frame").classList.add("idle"));
await page.waitForTimeout(400);
const idleHides = await page.evaluate(() =>
  getComputedStyle(document.getElementById("nowPlate")).opacity);
await page.evaluate(() => document.querySelector(".screen-frame").classList.remove("idle"));
ok("idle full screen hides it with the transport", idleHides === "0", `opacity=${idleHides}`);
await page.evaluate(() => document.exitFullscreen && document.exitFullscreen());
await page.waitForFunction(() => document.fullscreenElement === null, { timeout: 5000 })
  .catch(() => {});

// ── narrow viewport: it must not push the page sideways ─────────────────────
await page.setViewportSize({ width: 390, height: 780 });
await page.waitForTimeout(400);
const overflow = await page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);
ok("no horizontal overflow at 390px", overflow <= 0, `overflow=${overflow}px`);
const fits = await page.evaluate(() => {
  const p = document.getElementById("nowPlate").getBoundingClientRect();
  const f = document.querySelector(".screen-frame").getBoundingClientRect();
  return p.right <= f.right + 1 && p.left >= f.left - 1;
});
ok("plate stays inside the frame on mobile", fits);
await page.screenshot({ path: join(OUTDIR, "mobile.png") });

ok("no uncaught page errors", pageErrors.length === 0, pageErrors.join(" | ").slice(0, 200));

await browser.close();
server.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed; screenshots in ${OUTDIR}`);
process.exit(failed.length ? 1 : 0);
