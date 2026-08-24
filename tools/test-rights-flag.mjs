/* Real-browser test of SEC.05, the Rights Desk: the provenance copy, and the
 * flag link that has to carry a usable timestamp into the viewer's mail app.
 *   node tools/test-rights-flag.mjs
 * Same harness as the other three — site/ over http, driven by Playwright.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HOME = process.env.HOME || "";
const PLAYWRIGHT = process.env.PLAYWRIGHT || `${HOME}/daily-bread/db-render/node_modules/playwright/index.mjs`;
const CHROME = process.env.CHROME || `${HOME}/.cache/puppeteer/chrome/linux-150.0.7871.24/chrome-linux64/chrome`;
const ROOT = process.env.SITE_DIR || join(dirname(fileURLToPath(import.meta.url)), "..", "site");
const PORT = Number(process.env.PORT || 8791);

const { chromium } = await import(PLAYWRIGHT);

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

const browser = await chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });

/* Both title paths are stubbed rather than left to the network. Whether this
   harness can reach the real tower decides which one the page takes, and a test
   that lets it decide asserts whatever happened to be true that minute — the
   first version of this file passed on the fallback path only because the live
   fetch had not come back yet. abortTower() forces the grid; fakeTower() forces
   a title from master control. */
const TOWER = "**/api/status";
const abortTower = (page) => page.route(TOWER, (r) => r.abort());
const fakeTower = (page, streamTitle) => page.route(TOWER, (r) => r.fulfill({
  status: 200, contentType: "application/json",
  body: JSON.stringify({ online: true, viewerCount: 3, streamTitle }),
}));
const parts = (href) => {
  const q = href.slice(href.indexOf("?") + 1);
  const out = { to: href.slice("mailto:".length, href.indexOf("?")) };
  for (const kv of q.split("&")) {
    const i = kv.indexOf("=");
    out[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1).replace(/\+/g, " "));
  }
  return out;
};

/* ---------- desktop ---------- */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await abortTower(page);
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  await page.waitForTimeout(400);

  ok("SEC.05 tab exists", (await page.$("#tab-rights")) !== null);
  await page.click("#tab-rights");
  await page.waitForTimeout(200);

  const shown = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".panels > .panel"))
      .filter((p) => getComputedStyle(p).display !== "none").map((p) => p.id));
  ok("SEC.05 shows alone", shown.length === 1 && shown[0] === "rights", shown.join(","));

  const copy = await page.evaluate(() => document.getElementById("rights").textContent);
  ok("names where the material came from", /Internet Archive/.test(copy));
  ok("names the licence filter", /licenseurl:\(\*publicdomain\*\)/.test(copy));
  ok("says a mark is a claim, not a ruling", /not a legal opinion/i.test(copy));
  ok("separates what the station made itself", /Ground Zero/.test(copy) && /made at the station/i.test(copy));

  // the readout — the half of the claim the viewer cannot write themselves
  const card = await page.evaluate(() => ({
    title: document.getElementById("flagTitle").textContent,
    src: document.getElementById("flagSrc").textContent,
    slot: document.getElementById("flagSlot").textContent,
    local: document.getElementById("flagLocal").textContent,
    utc: document.getElementById("flagUtc").textContent,
  }));
  ok("readout names the programme", card.title.length > 1 && card.title !== "—", card.title);
  ok("readout says the title came from the grid", card.src === "FROM GRID", card.src);
  ok("readout names the slot", /^[A-Z]+ \d\d:\d\d · /.test(card.slot), card.slot);
  ok("local stamp carries its UTC offset", /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC[+-]\d\d:\d\d$/.test(card.local), card.local);
  ok("UTC stamp is ISO", /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(card.utc), card.utc);


  // the mailto: everything above has to survive into the message
  const href = await page.getAttribute("#flagMail", "href");
  const m = parts(href);
  ok("flag link is a mailto", href.startsWith("mailto:"), href.slice(0, 40));
  ok("mailto addresses the station", m.to === "ch0@ripostelabs.xyz", m.to);
  ok("subject marks it a rights claim", /rights claim/i.test(m.subject), m.subject);
  ok("subject carries the programme", m.subject.includes(card.title), m.subject);
  ok("body carries the programme", m.body.includes(`PROGRAMME:   ${card.title}`));
  ok("body carries the slot", m.body.includes(card.slot));
  ok("body carries both stamps", m.body.includes(card.local) && m.body.includes(card.utc));
  ok("body says the title came from the grid", /TITLE FROM:  today's schedule/.test(m.body), m.body.split("\n")[2]);
  ok("body records whether they were watching", /WATCHING:    no/.test(m.body));
  ok("body leaves the viewer room to write", /not in the public domain/.test(m.body) && /how to reach you/.test(m.body));

  // the point of the whole thing: the stamp is the moment, not page load
  const before = parts(await page.getAttribute("#flagMail", "href")).body;
  await page.waitForTimeout(1400);
  const after = parts(await page.getAttribute("#flagMail", "href")).body;
  ok("the stamp follows the clock", before !== after);

  // pointerdown refreshes it once more, so the click and the stamp agree
  await page.evaluate(() => document.getElementById("flagMail")
    .dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })));
  const onClick = parts(await page.getAttribute("#flagMail", "href")).body;
  ok("pointerdown re-stamps the link", onClick !== after);

  ok("no page errors", pageErrors.length === 0, pageErrors.join(" | "));
  await ctx.close();
}

/* ---------- the tower is up: the claim must name what master control set ----------
   The station's own title wins over the grid, and it arrives wearing the
   "CH0 · " prefix that the picture already says — the claim wants the
   programme's name, not the channel's. */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await fakeTower(page, "CH0 · THE SECOND WOMAN (1951)");
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  await page.waitForTimeout(700);
  await page.click("#tab-rights");
  await page.waitForTimeout(1200);

  const card = await page.evaluate(() => ({
    title: document.getElementById("flagTitle").textContent,
    src: document.getElementById("flagSrc").textContent,
  }));
  ok("live title beats the grid", card.title === "THE SECOND WOMAN (1951)", card.title);
  ok("readout says the title came from the tower", card.src === "FROM TOWER", card.src);

  const m = parts(await page.getAttribute("#flagMail", "href"));
  ok("subject carries the live title", m.subject.includes("THE SECOND WOMAN (1951)"), m.subject);
  ok("body says the title came from the tower", /TITLE FROM:  the tower, live/.test(m.body));
  ok("body still carries the slot the grid expected", /SLOT:        [A-Z]+ \d\d:\d\d · /.test(m.body));
  await ctx.close();
}

/* ---------- no JS: the desk must still be reachable ---------- */
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, javaScriptEnabled: false });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
  const href = await page.getAttribute("#flagMail", "href");
  ok("no JS: flag link is still a live mailto", href.startsWith("mailto:ch0@ripostelabs.xyz"), href);
  const visible = await page.evaluate(() =>
    getComputedStyle(document.getElementById("rights")).display !== "none");
  ok("no JS: SEC.05 is part of the long page", visible);
  await ctx.close();
}

await browser.close();
server.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
