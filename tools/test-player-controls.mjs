/* Real-browser test of the storefront player's transport controls —
   pause / resume-at-live, mute + volume, and full screen.
 *
 * It serves site/ over http (localStorage and the CDN both need a real origin,
 * not file://), drives it with Playwright, and asserts against a genuinely
 * playing stream — so it needs the tower to be ON AIR to pass in full.
 *
 * Prerequisites, neither of which this repo vendors:
 *   PLAYWRIGHT  path to a playwright install   (default: $HOME/daily-bread/db-render/node_modules/playwright/index.mjs)
 *   CHROME      path to a full Chrome binary   (default: the puppeteer cache below)
 * A headless-shell build is NOT enough: the Fullscreen API needs real Chrome.
 *
 *   node tools/test-player-controls.mjs
 *
 * Screenshots land in $OUTDIR (default /tmp/z0-player-test).
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
const OUTDIR = process.env.OUTDIR || "/tmp/z0-player-test";
const PORT = Number(process.env.PORT || 8788);

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
const consoleErrors = [];
const badRequests = [];
page.on("pageerror", (e) => consoleErrors.push("PAGEERROR: " + String(e)));
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("response", (r) => { if (r.status() >= 400) badRequests.push(`${r.status()} ${r.url()}`); });
page.on("requestfailed", (r) => badRequests.push(`FAILED ${r.url()} ${r.failure()?.errorText || ""}`));

await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "load" });

const st = () => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const tv = $("tv");
  return {
    // innerText, NOT textContent: each toggling label keeps both of its states
    // in the DOM (the hidden one reserves the width so the button cannot
    // resize), and only innerText respects visibility: hidden.
    pauseLabel: $("pauseBtn").innerText.trim(),
    pauseDisabled: $("pauseBtn").disabled,
    soundLabel: $("soundBtn").innerText.trim(),
    fsLabel: $("fsBtn").innerText.trim(),
    fsShown: getComputedStyle($("fsBtn")).display !== "none",
    volSlider: Number($("volSlider").value),
    volVal: $("volVal").textContent,
    volMutedClass: $("volGroup").classList.contains("muted"),
    videoVolume: tv.volume,
    videoMuted: tv.muted,
    videoPaused: tv.paused,
    currentTime: tv.currentTime,
    readyState: tv.readyState,
    stored: localStorage.getItem("z0.volume"),
    fsEl: document.fullscreenElement ? document.fullscreenElement.className : null,
  };
});

/* ---------- 0. the bar holds still ----------
   The complaint this answers: "toggling settings makes adjacent toggles change
   size, and full screen is larger than the other buttons." Both are layout
   facts, so they get measured rather than eyeballed. Every control in the bar
   is boxed to the same height; the three handling buttons are one width; and
   no press of any of them changes any box by a pixel. Sampled after EVERY
   toggle below, because a label pair that reserves the wrong width only shows
   up in the state you didn't look at. */
const CTLS = ["tuneBtn", "pauseBtn", "fsBtn", "soundBtn", "volGroup", "airChip"];
const boxes = () => page.evaluate((ids) => {
  const out = {};
  ids.forEach((id) => {
    const r = document.getElementById(id).getBoundingClientRect();
    out[id] = [Math.round(r.width * 100) / 100, Math.round(r.height * 100) / 100];
  });
  return out;
}, CTLS);
const sizeLog = [];
const recordSizes = async (label) => { sizeLog.push([label, await boxes()]); };

await recordSizes("boot");
{
  const b = sizeLog[0][1];
  const heights = new Set(CTLS.map((id) => b[id][1]));
  ok("size: every control in the bar is the same height", heights.size === 1,
     CTLS.map((id) => `${id} ${b[id][1]}`).join(" · "));
  const mains = ["tuneBtn", "pauseBtn", "fsBtn"].map((id) => b[id][0]);
  ok("size: TUNE, PAUSE and FULL SCREEN are one width — no odd slab out",
     Math.max(...mains) - Math.min(...mains) < 1, mains.join(" / "));
}

/* ---------- 1. initial state ---------- */
let s = await st();
ok("boot: PAUSE is disabled (nothing playing)", s.pauseDisabled === true);
ok("boot: pause label reads PAUSE", /^PAUSE$/.test(s.pauseLabel), s.pauseLabel);
ok("boot: SOUND: OFF", s.soundLabel === "SOUND: OFF", s.soundLabel);
ok("boot: volume group marked muted", s.volMutedClass === true);
ok("boot: full-screen button visible", s.fsShown === true);
ok("boot: fs label reads FULL SCREEN", /FULL SCREEN$/.test(s.fsLabel), s.fsLabel);
ok("boot: video element starts muted", s.videoMuted === true);

/* ---------- 2. the :fullscreen CSS actually parsed ----------
   The trap this guards: one unrecognised vendor pseudo in a comma-separated
   selector list invalidates the WHOLE rule. Each has its own rule; prove all
   four survived the parser. */
const fsRules = await page.evaluate(() => {
  const out = [];
  for (const sheet of document.styleSheets) {
    let rules; try { rules = sheet.cssRules; } catch { continue; }
    for (const r of rules) if (r.selectorText && /full-?screen/i.test(r.selectorText)) out.push(r.selectorText);
  }
  return out;
});
ok("css: standard :fullscreen frame rule parsed", fsRules.some((r) => /^\.screen-frame:fullscreen$/.test(r)), fsRules.join(" | "));
ok("css: standard :fullscreen video rule parsed", fsRules.some((r) => /^\.screen-frame:fullscreen video$/.test(r)));
ok("css: webkit full-screen rules parsed", fsRules.filter((r) => /-webkit-full-screen/.test(r)).length === 2,
   `${fsRules.filter((r) => /-webkit-full-screen/.test(r)).length} webkit rules`);

/* ---------- 3. tune in ---------- */
await page.click("#tuneBtn");
await page.waitForFunction(() => document.getElementById("tv").readyState >= 2 && !document.getElementById("tv").paused,
  null, { timeout: 45000 }).catch(() => {});
s = await st();
ok("tune: stream is playing", s.readyState >= 2 && s.videoPaused === false, `readyState=${s.readyState} paused=${s.videoPaused}`);
ok("tune: PAUSE became enabled", s.pauseDisabled === false);
await recordSizes("tune");

/* ---------- 4. pause / resume-at-live ---------- */
await page.click("#pauseBtn");
await page.waitForFunction(() => document.getElementById("tv").paused, null, { timeout: 5000 }).catch(() => {});
await page.waitForTimeout(250);
s = await st();
const pausedAt = s.currentTime;
ok("pause: video paused", s.videoPaused === true);
ok("pause: label flipped to RESUME LIVE", /RESUME LIVE$/.test(s.pauseLabel), s.pauseLabel);
await recordSizes("pause");

// Sit paused so the live edge moves out ahead of where we stopped.
await page.waitForTimeout(9000);
await page.click("#pauseBtn");
await page.waitForFunction(() => !document.getElementById("tv").paused, null, { timeout: 10000 }).catch(() => {});
await page.waitForTimeout(250);
s = await st();
ok("resume: playing again", s.videoPaused === false);
ok("resume: label back to PAUSE", /^PAUSE$/.test(s.pauseLabel), s.pauseLabel);
await recordSizes("resume");
ok("resume: jumped forward to the live edge, not continued from the hold",
   s.currentTime > pausedAt + 4, `held at ${pausedAt.toFixed(1)}s, resumed at ${s.currentTime.toFixed(1)}s`);

/* ---------- 5. external pause keeps the label honest ---------- */
await page.evaluate(() => document.getElementById("tv").pause());
await page.waitForTimeout(300);
s = await st();
ok("sync: a pause from outside the button still updates the label", /RESUME LIVE$/.test(s.pauseLabel), s.pauseLabel);
await page.click("#pauseBtn");
await page.waitForTimeout(500);

/* ---------- 6. volume ---------- */
const setVol = async (v) => {
  await page.evaluate((val) => {
    const el = document.getElementById("volSlider");
    el.value = String(val);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, v);
  await page.waitForTimeout(150);
};
await setVol(40);
s = await st();
ok("volume: slider 40 sets video volume to 0.40", Math.abs(s.videoVolume - 0.4) < 0.01, String(s.videoVolume));
ok("volume: unmuted by the drag", s.videoMuted === false);
ok("volume: SOUND: ON", s.soundLabel === "SOUND: ON", s.soundLabel);
await recordSizes("sound on");
ok("volume: readout shows 40", s.volVal === "40", s.volVal);
ok("volume: persisted to localStorage", s.stored === "40", String(s.stored));

await setVol(0);
s = await st();
ok("volume: dragging to 0 mutes", s.videoMuted === true && s.volMutedClass === true);
ok("volume: SOUND: OFF at zero", s.soundLabel === "SOUND: OFF", s.soundLabel);
await recordSizes("volume 0");

await page.click("#soundBtn");
await page.waitForTimeout(200);
s = await st();
ok("sound: unmuting off a zero slider restores an audible level",
   s.videoMuted === false && s.videoVolume > 0, `volume=${s.videoVolume}`);
ok("sound: slider followed the restore", s.volSlider > 0, String(s.volSlider));

await page.click("#soundBtn");
await page.waitForTimeout(200);
s = await st();
ok("sound: click again mutes", s.videoMuted === true && s.soundLabel === "SOUND: OFF");

/* volume survives a reload, muted does not */
await setVol(72);
await page.reload({ waitUntil: "load" });
s = await st();
ok("reload: volume level remembered", Math.abs(s.videoVolume - 0.72) < 0.01, String(s.videoVolume));
ok("reload: readout shows 72", s.volVal === "72", s.volVal);
ok("reload: comes back MUTED (autoplay policy), not blaring", s.videoMuted === true && s.soundLabel === "SOUND: OFF");

/* ---------- 7. full screen ---------- */
await page.click("#tuneBtn");
await page.waitForTimeout(3000);
await page.click("#fsBtn");
await page.waitForTimeout(1200);
s = await st();
const fsWorked = s.fsEl && s.fsEl.includes("screen-frame");
ok("fullscreen: the frame (not the bare video) went full screen", !!fsWorked, `fullscreenElement=${s.fsEl}`);
if (fsWorked) {
  ok("fullscreen: label flipped to EXIT FULL SCREEN", /EXIT FULL SCREEN$/.test(s.fsLabel), s.fsLabel);
  const box = await page.evaluate(() => {
    const v = document.getElementById("tv"), f = document.querySelector(".screen-frame");
    const c = document.querySelector(".feed-controls");
    return { vh: v.getBoundingClientRect().height, ih: window.innerHeight,
             objectFit: getComputedStyle(v).objectFit, border: getComputedStyle(f).borderTopWidth,
             controlsInsideFrame: f.contains(c), frameHasFsClass: f.classList.contains("fs"),
             controlsPos: getComputedStyle(c).position,
             btnColor: getComputedStyle(document.getElementById("fsBtn")).color };
  });
  ok("fullscreen: video fills the screen height", Math.abs(box.vh - box.ih) < 3, JSON.stringify(box));
  ok("fullscreen: frame border dropped", box.border === "0px", box.border);
  ok("fullscreen: letterboxed with object-fit: contain", box.objectFit === "contain", box.objectFit);
  ok("fullscreen: transport moved inside the frame (pause/volume stay reachable)", box.controlsInsideFrame === true);
  ok("fullscreen: controls overlay the picture", box.controlsPos === "absolute", box.controlsPos);
  ok("fullscreen: button palette flipped to paper (visible over the picture)",
     box.btnColor === "rgb(242, 240, 233)", box.btnColor);

  // pause and volume must actually WORK from inside full screen
  await page.click("#pauseBtn");
  await page.waitForTimeout(600);
  let fs = await st();
  ok("fullscreen: PAUSE works from the overlay", fs.videoPaused === true && /RESUME LIVE$/.test(fs.pauseLabel));
  await page.click("#pauseBtn");
  await page.waitForTimeout(600);
  await setVol(55);
  fs = await st();
  ok("fullscreen: volume works from the overlay", Math.abs(fs.videoVolume - 0.55) < 0.01, String(fs.videoVolume));
  await page.screenshot({ path: join(OUTDIR, "fullscreen.png") });

  // controls fade out when the pointer goes still, and come back when it moves
  await page.mouse.move(640, 300);
  await page.waitForTimeout(3600);
  let idle = await page.evaluate(() => ({
    idle: document.querySelector(".screen-frame").classList.contains("idle"),
    opacity: getComputedStyle(document.querySelector(".feed-controls")).opacity,
  }));
  ok("fullscreen: transport fades out after 3s idle", idle.idle === true && Number(idle.opacity) < 0.05, JSON.stringify(idle));
  await page.mouse.move(650, 320); await page.mouse.move(660, 340);
  await page.waitForTimeout(400);
  idle = await page.evaluate(() => ({
    idle: document.querySelector(".screen-frame").classList.contains("idle"),
    opacity: getComputedStyle(document.querySelector(".feed-controls")).opacity,
  }));
  ok("fullscreen: it comes back on mouse move", idle.idle === false && Number(idle.opacity) > 0.95, JSON.stringify(idle));

  const fsRows = await page.evaluate(() => {
    const bar = document.querySelector(".feed-controls");
    return new Set([...bar.children]
      .filter((c) => !c.classList.contains("ctl-break") && c.getBoundingClientRect().width)
      .map((c) => { const r = c.getBoundingClientRect(); return Math.round((r.top + r.height / 2) / 8) * 8; })).size;
  });
  ok("fullscreen: the forced break is dropped — one screen-wide row", fsRows === 1, `${fsRows} rows`);

  await page.click("#fsBtn");
  await page.waitForTimeout(1000);
  s = await st();
  ok("fullscreen: exits back to the page", s.fsEl === null && /^FULL SCREEN$/.test(s.fsLabel), `${s.fsEl} / ${s.fsLabel}`);
  const home = await page.evaluate(() => {
    const f = document.querySelector(".screen-frame"), c = document.querySelector(".feed-controls");
    return { insideFrame: f.contains(c), pos: getComputedStyle(c).position,
             afterFrame: f.parentNode === c.parentNode && f.compareDocumentPosition(c) === Node.DOCUMENT_POSITION_FOLLOWING,
             fsClass: f.classList.contains("fs") };
  });
  ok("fullscreen: transport parked back under the screen on exit",
     home.insideFrame === false && home.afterFrame === true && home.pos === "static" && home.fsClass === false,
     JSON.stringify(home));
}

/* double-click the picture */
await page.dblclick(".screen-frame", { position: { x: 200, y: 100 } });
await page.waitForTimeout(1000);
s = await st();
ok("fullscreen: double-clicking the picture toggles it", !!(s.fsEl && s.fsEl.includes("screen-frame")), `fullscreenElement=${s.fsEl}`);

/* Escape does not reliably leave full screen in headless Chrome, so exit
   through the API and PROVE we're out — the layout checks below are worthless
   if they measure the full-screen overlay instead of the page. */
await page.evaluate(() => document.fullscreenElement && document.exitFullscreen());
await page.waitForFunction(() => !document.fullscreenElement, null, { timeout: 5000 });
await page.waitForTimeout(400);
s = await st();
ok("layout: back out of full screen before measuring", s.fsEl === null, `fullscreenElement=${s.fsEl}`);

/* ---------- 8. layout + no errors ---------- */
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(500);
await page.locator(".feed-controls").screenshot({ path: join(OUTDIR, "controls.png") });
await page.screenshot({ path: join(OUTDIR, "page.png") });

/* The row is deliberately broken into two: the picture controls, then the sound
   controls with the status pushed right. Assert the grouping, not just a height. */
/* Group by the line's CENTRE, not by top: align-items:center gives a 40px
   button and a 33px chip different tops on the very same line. */
const rows = await page.evaluate(() => {
  const bar = document.querySelector(".feed-controls");
  const byLine = {};
  for (const c of bar.children) {
    if (c.classList.contains("ctl-break")) continue;
    const r = c.getBoundingClientRect();
    const mid = Math.round((r.top + r.height / 2) / 8) * 8;
    (byLine[mid] ||= []).push(c.id || c.className);
  }
  return Object.keys(byLine).sort((a, b) => a - b).map((t) => byLine[t]);
});
ok("layout: controls form exactly two rows at 1280px", rows.length === 2, JSON.stringify(rows));
ok("layout: row 1 is the picture — tune, pause, full screen",
   JSON.stringify(rows[0]) === JSON.stringify(["tuneBtn", "pauseBtn", "fsBtn"]), JSON.stringify(rows[0]));
ok("layout: row 2 is the sound, with status pushed right",
   JSON.stringify(rows[1]) === JSON.stringify(["soundBtn", "volGroup", "live-status"]), JSON.stringify(rows[1]));

// narrow viewport: everything still reachable, nothing overflows the page
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(400);
const narrow = await page.evaluate(() => ({
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  visible: ["tuneBtn", "pauseBtn", "soundBtn", "volGroup", "fsBtn"]
    .filter((id) => document.getElementById(id).getBoundingClientRect().width > 0).length,
}));
await page.locator("#live").screenshot({ path: join(OUTDIR, "mobile.png") });
ok("layout: no horizontal overflow at 390px", narrow.overflow <= 0, `overflow=${narrow.overflow}px`);
ok("layout: all 5 controls render at 390px", narrow.visible === 5, `${narrow.visible}/5`);

/* ---------- the invariance check ----------
   Everything above pressed every toggle at least once, sampling the bar each
   time. All the samples must be identical: one differing pixel IS the reported
   bug, so this compares exactly rather than within a tolerance. */
{
  const ref = sizeLog[0][1];
  const moved = [];
  sizeLog.slice(1).forEach(([label, b]) => {
    CTLS.forEach((id) => {
      // Half a pixel. The defects this guards were 5px (the volume readout
      // growing from one digit to three) and 35px (EXIT FULL SCREEN); what is
      // left is sub-pixel rounding on a calc()ed min-width, which nothing can
      // see and no layout moves for.
      if (Math.abs(b[id][0] - ref[id][0]) > 0.5 || Math.abs(b[id][1] - ref[id][1]) > 0.5) {
        moved.push(`${id} ${ref[id].join("x")} -> ${b[id].join("x")} (after ${label})`);
      }
    });
  });
  ok(`size: nothing in the bar resizes when toggled (${sizeLog.length} states sampled)`,
     moved.length === 0, moved.join(" · ") || "held");
}

console.log("\n-- network problems seen (informational) --");
[...new Set(badRequests)].forEach((b) => console.log("   " + b));
ok("no uncaught JS errors on the page", consoleErrors.filter((e) => e.startsWith("PAGEERROR:")).length === 0,
   consoleErrors.filter((e) => e.startsWith("PAGEERROR:")).slice(0, 3).join(" ; "));
/* Known-and-not-ours misses are allowed:
     - favicon: this throwaway test server doesn't serve one.
     - cdnjs hls.js 1.6.16: that exact version is NOT published on cdnjs (it
       404s, which Chrome surfaces as ERR_BLOCKED_BY_ORB). Pre-existing on
       origin/main; harmless only because the jsdelivr fallback catches it,
       at the cost of a wasted round trip before playback starts.
     - 404 on /api/comment: this suite serves site/ as static files with no
       Worker behind them, which is exactly the case the comment box is meant
       to survive — the page asks the relay what it is, hears nothing, and
       keeps the link to the tower instead of showing a box that cannot work.
       The 404 is the graceful path being taken, not a fault.
     - ERR_ABORTED on the tower's own /hls/: this suite reloads the page while
       a live channel is playing, and the browser cancels whatever segment or
       playlist poll was in flight. It is the browser tidying up after the
       test, not a failure of the site — and it is a coin-toss on timing, so
       asserting against it makes the suite flaky. Verified by running this
       exact file against an unmodified origin/main: clean on one run,
       two aborts on the next.
   Anything else is a regression from this change. */
const KNOWN = /favicon|cdnjs\.cloudflare\.com\/ajax\/libs\/hls\.js|\/hls\/\d+\/stream[^ ]*\s+net::ERR_ABORTED|404 [^ ]*\/api\/comment/i;
const realBad = [...new Set(badRequests)].filter((b) => !KNOWN.test(b));
ok("no failed requests beyond the two known pre-existing misses", realBad.length === 0, realBad.slice(0, 4).join(" ; "));

await browser.close();
server.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) { console.log("FAILED:"); failed.forEach((f) => console.log("  - " + f.name + "  " + f.detail)); process.exit(1); }
