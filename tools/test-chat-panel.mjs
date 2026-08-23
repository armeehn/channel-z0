/* Real-browser test of the live chat in SEC.01's rail.
 *
 * Three things are under test and they fail in different ways:
 *   1. the rail itself — SPEC and CHAT share one card, one at a time, with the
 *      keyboard and the remembered choice both working;
 *   2. the wire — register, backlog, websocket, all cross-origin to the tower.
 *      This half needs the real tower reachable; it is skipped, loudly, if it
 *      is not;
 *   3. the sanitiser — chat bodies are HTML somebody else wrote, and this page
 *      has no CSP, so anything that can run must not survive the render. Driven
 *      through window.__z0ChatInternals rather than by posting hostile text
 *      into a real room.
 *
 * Prerequisites (not vendored):
 *   PLAYWRIGHT  path to a playwright install
 *   CHROME      path to a full Chrome binary
 *
 *   node tools/test-chat-panel.mjs
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
const OUTDIR = process.env.OUTDIR || "/tmp/z0-chat-test";
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
page.on("pageerror", (e) => pageErrors.push(String(e)));

await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });
await page.waitForTimeout(400);

/* ---------- 1. the rail ---------- */
const rail = () => page.evaluate(() => ({
  chatShown: !document.getElementById("rail-chat").hidden,
  specShown: !document.getElementById("rail-spec").hidden,
  chatSel: document.getElementById("rtab-chat").getAttribute("aria-selected"),
  specSel: document.getElementById("rtab-spec").getAttribute("aria-selected"),
  chatTab: document.getElementById("rtab-chat").tabIndex,
  specTab: document.getElementById("rtab-spec").tabIndex,
  chatDisplay: getComputedStyle(document.getElementById("rail-chat")).display,
  specDisplay: getComputedStyle(document.getElementById("rail-spec")).display,
}));

let r = await rail();
ok("rail: opens on CHAT", r.chatShown === true && r.specShown === false, JSON.stringify(r));
ok("rail: aria-selected follows the panel", r.chatSel === "true" && r.specSel === "false");
ok("rail: only the selected tab is in the tab order", r.chatTab === 0 && r.specTab === -1);
/* The [hidden] trap: an attribute selector must out-specify the class that
   sets display, or the panel stays on the page while claiming to be hidden. */
ok("rail: [hidden] actually removes the panel from layout", r.specDisplay === "none", r.specDisplay);

await page.click("#rtab-spec");
await page.waitForTimeout(120);
r = await rail();
ok("rail: SPEC selects", r.specShown === true && r.chatShown === false && r.specSel === "true");
const rowsVisible = await page.evaluate(() =>
  Array.from(document.querySelectorAll("#live .spec-row")).filter((e) => e.getBoundingClientRect().height > 0).length);
ok("rail: the twelve SPEC rows are still there and laid out", rowsVisible === 12, String(rowsVisible));
/* The hover notes hang off the LEFT of the card, out over the picture column.
   The panel itself has always been a scroller (that is the pinned layout), so
   what matters is not "is there a scroller above me" but "does the note still
   land on screen, unclipped, inside it". Assert that instead — and only walk
   the rail's own subtree for scrollers, since the rail is the part this change
   introduced. */
const railScrollers = await page.evaluate(() => {
  const rail = document.querySelector("#live .rail");
  const note = document.querySelector("#live .spec-note");
  return Array.from(rail.querySelectorAll("*")).concat([rail])
    // the note itself is overflow:hidden by design (it collapses to zero
    // height while closed so it stops inflating scrollHeight) — ancestors only
    .filter((e) => e !== note && e.contains(note))
    .filter((e) => { const o = getComputedStyle(e); return o.overflowX !== "visible" || o.overflowY !== "visible"; })
    .map((e) => e.id || e.className);
});
ok("rail: the rail puts no scroller around the SPEC hover notes", railScrollers.length === 0, railScrollers.join(",") || "clear");

await page.hover("#live .spec-row");
await page.waitForTimeout(220);
const note = await page.evaluate(() => {
  const n = document.querySelector("#live .spec-note");
  const b = n.getBoundingClientRect();
  const p = document.getElementById("live").getBoundingClientRect();
  return { w: Math.round(b.width), h: Math.round(b.height), left: Math.round(b.left),
           vis: getComputedStyle(n).visibility, op: getComputedStyle(n).opacity,
           insidePanelLeft: b.left >= p.left - 1, onScreen: b.left >= 0 && b.right <= window.innerWidth };
});
ok("rail: a hover note still opens, at full size and on screen",
   note.vis === "visible" && Number(note.op) > 0.9 && note.h > 40 && note.onScreen && note.insidePanelLeft,
   JSON.stringify(note));

/* keyboard: the pair is one tablist */
await page.focus("#rtab-spec");
await page.keyboard.press("ArrowLeft");
await page.waitForTimeout(120);
r = await rail();
ok("rail: arrow keys move between SPEC and CHAT", r.chatShown === true, JSON.stringify(r));

/* the choice is remembered */
await page.click("#rtab-spec");
await page.waitForTimeout(120);
await page.reload({ waitUntil: "load" });
await page.waitForTimeout(500);
r = await rail();
ok("rail: the viewer's choice survives a reload", r.specShown === true, JSON.stringify(r));
await page.click("#rtab-chat");
await page.waitForTimeout(150);

/* ---------- 2. the wire ---------- */
const chatState = () => page.evaluate(() => ({
  state: document.getElementById("chatState").textContent.trim(),
  live: document.getElementById("chatState").classList.contains("live"),
  note: document.getElementById("chatNote").hidden ? null : document.getElementById("chatNote").textContent.trim(),
  msgs: document.querySelectorAll("#chatLog .chat-msg").length,
  user: (() => { try { return JSON.parse(localStorage.getItem("z0.chat.user") || "null"); } catch { return null; } })(),
}));

await page.waitForFunction(() => {
  const t = document.getElementById("chatState").textContent.trim();
  return t !== "—" && t !== "CONNECTING…";
}, { timeout: 20000 }).catch(() => {});
let c = await chatState();
const wired = c.state === "LIVE";
ok("chat: the websocket to the tower is live", wired, `state=${c.state}`);
if (!wired) console.log("   (tower unreachable from here — the wire half of this suite is not proving anything)");

if (wired) {
  ok("chat: a viewer token was registered and stored", !!(c.user && c.user.accessToken), c.user ? c.user.displayName : "none");
  const first = c.user && c.user.id;
  /* Registering once and keeping the token is what stops every page view
     announcing a new arrival in the tower's room: Owncast broadcasts
     USER_JOINED on a token's FIRST connection only. */
  await page.reload({ waitUntil: "load" });
  await page.waitForTimeout(2500);
  c = await chatState();
  ok("chat: a reload reuses the token instead of registering a new viewer",
     !!(c.user && c.user.id === first), `${first} -> ${c.user && c.user.id}`);

  const cfg = await page.evaluate(async () => {
    const r = await fetch("https://watch.ch0.ripostelabs.xyz/api/config", { cache: "no-store" });
    return r.json();
  });
  ok("chat: the tower's chat is actually open", cfg.chatDisabled === false, `chatDisabled=${cfg.chatDisabled}`);

  /* A message really sent by the tower has to land in the log. Rather than
     posting into a live room, replay one through the same entry point the
     websocket uses. */
  const landed = await page.evaluate(() => {
    window.__z0ChatInternals.appendMessage({
      id: "test-" + Math.random().toString(36).slice(2),
      type: "CHAT", timestamp: new Date().toISOString(),
      user: { displayName: "test-viewer", displayColor: 200 },
      body: "<p>hello from the <b>test</b></p>",
    });
    const el = document.querySelector("#chatLog .chat-msg:last-child");
    return { text: el.innerText.replace(/\s+/g, " ").trim(), bold: !!el.querySelector("b"),
             colour: el.querySelector(".who").style.color };
  });
  ok("chat: a message renders with its author, and safe markup survives",
     /test-viewer: hello from the test/.test(landed.text) && landed.bold === true, JSON.stringify(landed));
  ok("chat: the author's colour is taken down to something legible on paper",
     /hsl\(200,\s*58%,\s*30%\)/.test(landed.colour.replace(/\s+/g, " ")) || landed.colour.startsWith("rgb"),
     landed.colour);
}

/* ---------- 3. the sanitiser ---------- */
const hostile = await page.evaluate(() => {
  const cases = {
    script: '<script>window.__pwned = 1<\/script>hi',
    imgOnerror: '<img src=x onerror="window.__pwned=1">',
    imgOffPath: '<img src="https://watch.ch0.ripostelabs.xyz/hls/stream.m3u8">',
    jsHref: '<a href="javascript:window.__pwned=1">click</a>',
    iframe: '<iframe src="https://evil.example/"></iframe>caption',
    style: '<style>body{display:none}</style>text',
    svgOnload: '<svg onload="window.__pwned=1"><circle /></svg>',
    formAction: '<form action="https://evil.example"><input name="x"></form>',
    okLink: '<a href="https://example.com/x">a link</a>',
    okEmoji: '<img class="emoji" src="https://watch.ch0.ripostelabs.xyz/img/emoji/x.png" alt="x">',
    httpImg: '<img src="http://evil.example/track.gif">',
  };
  const out = {};
  for (const [k, html] of Object.entries(cases)) {
    const host = document.createElement("div");
    host.appendChild(window.__z0ChatInternals.sanitizeChatBody(html));
    out[k] = {
      html: host.innerHTML,
      text: host.textContent,
      tags: Array.from(host.querySelectorAll("*")).map((e) => e.tagName).join(","),
      handlers: Array.from(host.querySelectorAll("*")).some((e) =>
        Array.from(e.attributes).some((a) => /^on/i.test(a.name))),
    };
  }
  return { out, pwned: !!window.__pwned };
});
const h = hostile.out;
ok("sanitise: nothing executed while sanitising", hostile.pwned === false);
ok("sanitise: <script> is dropped, its text kept", !/script/i.test(h.script.html) && h.script.text.includes("hi"), h.script.html);
ok("sanitise: <img onerror> cannot survive", !h.imgOnerror.handlers && !/onerror/i.test(h.imgOnerror.html), h.imgOnerror.html);
ok("sanitise: javascript: hrefs are refused, the words stay", !/javascript:/i.test(h.jsHref.html) && h.jsHref.text.includes("click"), h.jsHref.html);
ok("sanitise: <iframe> is dropped", !/iframe/i.test(h.iframe.html) && h.iframe.text.includes("caption"), h.iframe.html);
ok("sanitise: <style> cannot reach the page", !/style/i.test(h.style.tags) && h.style.text.includes("text"), h.style.html);
ok("sanitise: <svg onload> is dropped", !/svg/i.test(h.svgOnload.tags) && !h.svgOnload.handlers, h.svgOnload.html);
ok("sanitise: <form> is dropped", !/form|input/i.test(h.formAction.tags), h.formAction.html);
ok("sanitise: no on* attribute survives anywhere",
   Object.values(h).every((v) => v.handlers === false));
ok("sanitise: an ordinary https link is kept, and made rel-safe",
   /href="https:\/\/example\.com\/x"/.test(h.okLink.html) && /noopener/.test(h.okLink.html) && /nofollow/.test(h.okLink.html), h.okLink.html);
ok("sanitise: a tower emoji image is kept", /img/i.test(h.okEmoji.tags) && /class="emoji"/.test(h.okEmoji.html), h.okEmoji.html);
ok("sanitise: a plain-http image (a tracking pixel) is refused", !/img/i.test(h.httpImg.tags), h.httpImg.html);
/* "https, and on the tower" is not enough: <img src=x> resolves against the
   tower and would otherwise pass as an emoji pointing anywhere on it. */
ok("sanitise: a tower image outside /img/ is refused", !/img/i.test(h.imgOffPath.tags), h.imgOffPath.html);
ok("sanitise: <img onerror> leaves no image at all", !/img/i.test(h.imgOnerror.tags), h.imgOnerror.html);

/* ---------- 4. it does not cost the pinned layout ---------- */
const fit = await page.evaluate(() => ({
  docScroll: document.documentElement.scrollHeight - document.documentElement.clientHeight,
  overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  panelOver: (() => { const p = document.getElementById("live"); return p.scrollHeight - p.clientHeight; })(),
  logScrolls: (() => { const l = document.getElementById("chatLog"); return getComputedStyle(l).overflowY; })(),
  logH: Math.round(document.getElementById("chatLog").getBoundingClientRect().height),
}));
ok("layout: the page still does not scroll at 1280x900", fit.docScroll <= 0 && fit.panelOver <= 0, JSON.stringify(fit));
ok("layout: no horizontal overflow", fit.overflowX <= 0, String(fit.overflowX));
ok("layout: the chat scrolls inside its own frame", fit.logScrolls === "auto", fit.logScrolls);
ok("layout: the chat gets a usable amount of column", fit.logH >= 180, `${fit.logH}px`);
await page.screenshot({ path: join(OUTDIR, "chat-1280.png") });

/* A long message must not push the rail wide. */
const overflowLong = await page.evaluate(() => {
  window.__z0ChatInternals.appendMessage({
    id: "long-1", type: "CHAT", timestamp: new Date().toISOString(),
    user: { displayName: "verbose-viewer", displayColor: 10 },
    body: "A".repeat(400) + " https://example.com/" + "b".repeat(200),
  });
  return { railW: Math.round(document.querySelector("#live .rail").getBoundingClientRect().width),
           overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
           logOver: document.getElementById("chatLog").scrollWidth - document.getElementById("chatLog").clientWidth };
});
ok("layout: an unbroken 600-character message does not widen anything",
   overflowLong.overflowX <= 0 && overflowLong.logOver <= 0 && overflowLong.railW === 292, JSON.stringify(overflowLong));

/* ---------- 5. phone ---------- */
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(300);
const narrow = await page.evaluate(() => ({
  overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  logH: Math.round(document.getElementById("chatLog").getBoundingClientRect().height),
  tabsVisible: !!document.getElementById("rtab-chat").getBoundingClientRect().width,
}));
ok("phone: no horizontal overflow at 390px", narrow.overflowX <= 0, String(narrow.overflowX));
ok("phone: the chat still has a readable height", narrow.logH >= 150, `${narrow.logH}px`);
ok("phone: the rail switch is reachable", narrow.tabsVisible === true);
await page.screenshot({ path: join(OUTDIR, "chat-390.png"), fullPage: true });

ok("no uncaught JS errors", pageErrors.length === 0, pageErrors.slice(0, 3).join(" ; "));

const failed = results.filter((x) => !x.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) { console.log("\nFAILURES:"); failed.forEach((f) => console.log("  - " + f.name + (f.detail ? "  — " + f.detail : ""))); }
console.log(`screenshots: ${OUTDIR}`);
await browser.close();
server.close();
process.exit(failed.length ? 1 : 0);
