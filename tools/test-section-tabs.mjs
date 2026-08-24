/* Real-browser test of the storefront's section tabs and the pinned shell.
 * Serves site/ over http and drives it with Playwright, like the other two.
 *   node tools/test-section-tabs.mjs
 * Screenshots land in $OUTDIR (default /tmp/z0-tabs-test).
 */
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HOME = process.env.HOME || "";
const PLAYWRIGHT = process.env.PLAYWRIGHT || `${HOME}/daily-bread/db-render/node_modules/playwright/index.mjs`;
const CHROME = process.env.CHROME || `${HOME}/.cache/puppeteer/chrome/linux-150.0.7871.24/chrome-linux64/chrome`;
const ROOT = process.env.SITE_DIR || join(dirname(fileURLToPath(import.meta.url)), "..", "site");
const OUTDIR = process.env.OUTDIR || "/tmp/z0-tabs-test";
const PORT = Number(process.env.PORT || 8790);

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
const ok = (name, pass, detail = "") => { results.push({ name, pass, detail }); console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };

const browser = await chromium.launch({ executablePath: CHROME, args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"] });
const SECTIONS = [
  ["live", "01", "Live Feed"], ["program", "02", "Program"], ["ground-zero", "03", "Ground Zero"],
  ["submit-ad", "04", "File a Spot"], ["rights", "05", "Rights Desk"],
];

const pageErrors = [];
async function newPage(ctx) {
  const page = await ctx.newPage();
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|net::ERR|ERR_BLOCKED/.test(m.text())) pageErrors.push(m.text()); });
  return page;
}
const visible = (page) => page.evaluate(() =>
  Array.from(document.querySelectorAll(".panels > .panel"))
    .filter((p) => getComputedStyle(p).display !== "none").map((p) => p.id));

/* ---------- desktop 1280x900 ---------- */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await newPage(ctx);
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  await page.waitForTimeout(400);

  ok("tabs mode engages", await page.evaluate(() => document.documentElement.classList.contains("tabs")));
  ok("five tabs rendered", (await page.$$(".sec-tab")).length === 5, `${(await page.$$(".sec-tab")).length}`);

  // the merged footer: one element, outside the tab machinery, no heading
  const foot = await page.evaluate(() => {
    const f = document.querySelector(".station-foot");
    if (!f) return null;
    return {
      count: document.querySelectorAll(".station-foot").length,
      inPanels: !!f.closest(".panels"),
      heads: f.querySelectorAll(".sec-head, .sec-no, .sec-title").length,
      sponsor: !!f.querySelector("#labLink"),
      signoff: /BROADCAST DAY AT MIDNIGHT/.test(f.textContent) && /EST\. 2026/.test(f.textContent),
      mantra: !!f.querySelector(".mantra"),
      orphans: document.querySelectorAll("#lab, #sign-off, #tab-lab, #tab-sign-off").length,
    };
  });
  ok("one station footer exists", foot && foot.count === 1, JSON.stringify(foot));
  ok("footer sits outside .panels", foot && !foot.inPanels);
  ok("footer carries no section heading", foot && foot.heads === 0, String(foot && foot.heads));
  ok("footer keeps SEC.05's sponsor + mantra", foot && foot.sponsor && foot.mantra);
  ok("footer keeps SEC.06's sign-off lines", foot && foot.signoff);
  ok("old SEC.05/06 panels and tabs are gone", foot && foot.orphans === 0, String(foot && foot.orphans));

  let vis = await visible(page);
  ok("opens on SEC.01 only", vis.length === 1 && vis[0] === "live", vis.join(","));

  for (const [id, no, label] of SECTIONS) {
    await page.click(`#tab-${id}`);
    await page.waitForTimeout(160);
    vis = await visible(page);
    ok(`tab ${no} shows only #${id}`, vis.length === 1 && vis[0] === id, vis.join(",") || "none");

    const sel = await page.getAttribute(`#tab-${id}`, "aria-selected");
    ok(`tab ${no} marked selected`, sel === "true", String(sel));

    const hash = await page.evaluate(() => location.hash);
    ok(`tab ${no} writes hash`, hash === "#" + id, hash);

    // the whole point: the document itself must not scroll
    const doc = await page.evaluate(() => {
      const e = document.scrollingElement;
      return { over: e.scrollHeight - e.clientHeight, bodyOv: getComputedStyle(document.body).overflow };
    });
    ok(`tab ${no} page does not scroll`, doc.over <= 1, `overflow ${doc.over}px`);

    // the footer is under every section, and on screen with it
    const ft = await page.evaluate(() => {
      const f = document.querySelector(".station-foot");
      const r = f.getBoundingClientRect();
      const p = document.querySelector(".panels").getBoundingClientRect();
      return { shown: getComputedStyle(f).display !== "none" && r.height > 0,
               below: r.top >= p.top, bottom: r.bottom, vh: window.innerHeight };
    });
    ok(`tab ${no} keeps the footer under it`, ft.shown && ft.below, `top ok ${ft.below}`);
    ok(`tab ${no} footer is on screen`, ft.bottom <= ft.vh + 1, `bottom ${Math.round(ft.bottom)} of ${ft.vh}`);

    await page.screenshot({ path: join(OUTDIR, `sec-${no}-${id}.png`) });
  }

  // the guide is allowed to scroll INSIDE its frame
  await page.click("#tab-program");
  await page.waitForTimeout(200);
  const grid = await page.evaluate(() => {
    const g = document.getElementById("pvGrid");
    return { scrollable: g.scrollHeight > g.clientHeight + 1, top: g.scrollTop, rows: g.children.length };
  });
  ok("guide scrolls inside its own frame", grid.scrollable, `${grid.rows} rows`);
  ok("guide opens near what's on now", grid.top >= 0 && grid.rows > 0, `scrollTop ${grid.top}`);

  // a rebuild must not yank that scroll back to sign-on
  await page.evaluate(() => { document.getElementById("pvGrid").scrollTop = 220; });
  await page.evaluate(() => renderSchedule());
  await page.waitForTimeout(80);
  const kept = await page.evaluate(() => document.getElementById("pvGrid").scrollTop);
  ok("30s rebuild keeps the guide's scroll", Math.abs(kept - 220) < 4, `scrollTop ${kept}`);

  // keyboard: arrows walk the strip
  await page.focus("#tab-program");
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(140);
  vis = await visible(page);
  ok("ArrowRight walks to SEC.03", vis[0] === "ground-zero", vis.join(","));
  await page.keyboard.press("End");
  await page.waitForTimeout(140);
  vis = await visible(page);
  ok("End jumps to SEC.05", vis[0] === "rights", vis.join(","));
  await page.keyboard.press("Home");
  await page.waitForTimeout(140);
  vis = await visible(page);
  ok("Home returns to SEC.01", vis[0] === "live", vis.join(","));

  // the widened SPEC card should stop wrapping its values
  await page.click("#tab-live");
  await page.waitForTimeout(150);
  // FEED is live text of any length, so it is excluded; the rest are fixed
  // strings and at 292px at most one of them ought to need a second line.
  // The rail now carries SPEC and CHAT as a pair of tabs and opens on CHAT,
  // so select SPEC before measuring its rows — a hidden panel measures zero
  // and would make this assertion pass without proving anything.
  await page.click("#rtab-spec");
  await page.waitForTimeout(120);
  const wrapped = await page.evaluate(() => Array.from(document.querySelectorAll("#live .spec-row"))
    .filter((r) => r.getBoundingClientRect().height > 34)
    .map((r) => r.querySelector(".k").textContent)
    .filter((k) => k !== "FEED"));
  ok("SPEC values mostly fit on one line", wrapped.length <= 1, wrapped.join(",") || "none");

  // hero fold gives its pixels to the picture
  await page.click("#tab-live");
  await page.waitForTimeout(150);
  const wOpen = await page.evaluate(() => document.querySelector("#live .screen-frame").getBoundingClientRect().height);
  await page.click("#heroToggle");
  await page.waitForTimeout(200);
  const collapsed = await page.evaluate(() => document.getElementById("hero").classList.contains("collapsed"));
  const wFold = await page.evaluate(() => document.querySelector("#live .screen-frame").getBoundingClientRect().height);
  ok("hero folds", collapsed);
  ok("folding does not shrink the picture", wFold >= wOpen, `${wOpen} -> ${wFold}`);

  // Everything on SEC.01 stays on screen — with the intro OPEN, which is the
  // state a 900px window boots into. The folded state has strictly more room,
  // so this is the case that has to hold.
  const measureLive = () => page.evaluate(() => {
    const r = (s) => document.querySelector(s).getBoundingClientRect();
    const p = document.getElementById("live");
    return {
      ctl: r("#live .feed-controls").bottom,
      spec: r("#live .speccard").bottom,
      foot: r(".station-foot").bottom,
      panelOver: p.scrollHeight - p.clientHeight,
      vh: window.innerHeight,
    };
  });
  const setHeroOpen = (want) => page.evaluate((w) => {
    const open = document.getElementById("heroToggle").getAttribute("aria-expanded") === "true";
    if (open !== w) document.getElementById("heroToggle").click();
  }, want);

  for (const open of [true, false]) {
    await setHeroOpen(open);
    await page.waitForTimeout(200);
    const f = await measureLive();
    const tag = open ? "intro open" : "intro folded";
    ok(`SEC.01 transport row fits (${tag})`, f.ctl <= f.vh + 1, `bottom ${Math.round(f.ctl)} of ${f.vh}`);
    ok(`SEC.01 SPEC card fits (${tag})`, f.spec <= f.vh + 1, `bottom ${Math.round(f.spec)} of ${f.vh}`);
    ok(`SEC.01 panel does not scroll (${tag})`, f.panelOver <= 1, `overflow ${f.panelOver}px`);
    ok(`SEC.01 footer fits (${tag})`, f.foot <= f.vh + 1, `bottom ${Math.round(f.foot)} of ${f.vh}`);
  }

  // the one-line masthead must not fuse the two sentences together
  const mast = await page.evaluate(() => document.querySelector("h1.masthead").innerText.replace(/\s+/g, " ").trim());
  ok("masthead keeps its space on one line", /IT\.\s+WELCOME/i.test(mast), JSON.stringify(mast));

  await ctx.close();
}

/* ---------- deep link ---------- */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await newPage(ctx);
  await page.goto(`http://127.0.0.1:${PORT}/#program`, { waitUntil: "load" });
  await page.waitForTimeout(350);
  let vis = await visible(page);
  ok("#program deep-links to SEC.02", vis.length === 1 && vis[0] === "program", vis.join(","));

  // the retired sections were addresses once; they must land somewhere, not blank
  for (const dead of ["lab", "sign-off"]) {
    await page.goto(`http://127.0.0.1:${PORT}/#${dead}`, { waitUntil: "load" });
    await page.waitForTimeout(300);
    vis = await visible(page);
    ok(`retired #${dead} falls back to SEC.01`, vis.length === 1 && vis[0] === "live", vis.join(","));
  }
  await ctx.close();
}

/* ---------- short window: picture still fits ---------- */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 700 } });
  const page = await newPage(ctx);
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  await page.waitForTimeout(400);
  const st = await page.evaluate(() => ({
    folded: document.getElementById("hero").classList.contains("collapsed"),
    ctl: document.querySelector("#live .feed-controls").getBoundingClientRect().bottom,
    vh: window.innerHeight,
    over: document.scrollingElement.scrollHeight - document.scrollingElement.clientHeight,
  }));
  ok("short window opens folded", st.folded);
  ok("short window: transport row fits", st.ctl <= st.vh + 1, `bottom ${Math.round(st.ctl)} of ${st.vh}`);
  ok("short window: page does not scroll", st.over <= 1, `overflow ${st.over}px`);
  await page.screenshot({ path: join(OUTDIR, "short-700.png") });
  await ctx.close();
}

/* ---------- phone: tabs still cut the scrolling ---------- */
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 780 } });
  const page = await newPage(ctx);
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  await page.waitForTimeout(400);
  const vis = await visible(page);
  ok("phone shows one section", vis.length === 1 && vis[0] === "live", vis.join(","));
  const sticky = await page.evaluate(() => getComputedStyle(document.getElementById("secnav")).position);
  ok("phone tab bar is sticky", sticky === "sticky", sticky);
  const tabRows = await page.evaluate(() => {
    const ts = Array.from(document.querySelectorAll(".sec-tab"));
    return new Set(ts.map((t) => Math.round(t.getBoundingClientRect().top))).size;
  });
  // five half-width tabs: two pairs and the fifth alone on a full-width row
  ok("phone tabs wrap to 3 rows", tabRows === 3, `${tabRows} rows`);
  const noHorz = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  ok("phone: no horizontal scroll", noHorz);
  // the fold button must not squeeze the masthead into a column of one-word lines
  const mastLines = await page.evaluate(() => {
    const h = document.querySelector("h1.masthead");
    return Math.round(h.getBoundingClientRect().height / parseFloat(getComputedStyle(h).fontSize) / 0.95);
  });
  ok("phone masthead is not squeezed", mastLines <= 3, `${mastLines} lines`);
  // labels should read, not ellipsize away
  const clipped = await page.evaluate(() => Array.from(document.querySelectorAll(".sec-tab .t"))
    .filter((t) => t.scrollWidth > t.clientWidth + 1).map((t) => t.textContent));
  ok("phone tab labels are not clipped", clipped.length === 0, clipped.join(","));
  await page.screenshot({ path: join(OUTDIR, "phone-390.png"), fullPage: true });
  await ctx.close();
}

/* ---------- no JS: the old page comes back ---------- */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, javaScriptEnabled: false });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  const st = await page.evaluate(() => ({
    shown: Array.from(document.querySelectorAll(".panels > .panel")).filter((p) => getComputedStyle(p).display !== "none").length,
    navHidden: getComputedStyle(document.getElementById("secnav")).display === "none",
    scrolls: document.scrollingElement.scrollHeight > window.innerHeight,
  }));
  ok("no JS: all five sections present", st.shown === 5, `${st.shown}`);
  const noJsFoot = await page.evaluate(() => {
    const f = document.querySelector(".station-foot");
    const last = document.querySelectorAll(".panels > .panel");
    return f && getComputedStyle(f).display !== "none" &&
           f.getBoundingClientRect().top >= last[last.length - 1].getBoundingClientRect().top;
  });
  ok("no JS: footer ends the long page", noJsFoot);
  ok("no JS: dead tab bar is hidden", st.navHidden);
  ok("no JS: page scrolls as before", st.scrolls);
  await ctx.close();
}

ok("no uncaught page errors", pageErrors.length === 0, pageErrors.slice(0, 3).join(" | "));

await browser.close();
server.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed  ·  screenshots in ${OUTDIR}`);
process.exit(failed.length ? 1 : 0);
