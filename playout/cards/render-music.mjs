// Render one Channel Z0 music card PNG per track.
//
// One browser, N screenshots — launching Chromium 73 times would dominate the
// runtime. Text is injected per track rather than templating 73 HTML files.
//
// Long titles are shrunk to fit rather than allowed to overflow: the card is
// 640x480 and some of these 78s have titles like "Crossing Over the Ferry" in
// one breath and a five-word subtitle in the next.
//
// --viz renders the card WITHOUT the static equaliser mark, for use as the
// backplate under tools/z0-music-viz.py. Two card sets can coexist; which one a
// track gets is decided at remux time, not here.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const argv = process.argv.slice(2);
const vizFlag = argv.findIndex(a => a === '--viz' || a.startsWith('--viz='));
const viz = vizFlag >= 0;
const vizMode = viz && argv[vizFlag].includes('=') ? argv[vizFlag].split('=')[1] : '1';
const htmlFlag = argv.indexOf('--html');
const htmlPath = htmlFlag >= 0 ? argv[htmlFlag + 1] : '/root/z0cards/music-card.html';
const pos = argv.filter((a, i) =>
  !a.startsWith('--') && !(htmlFlag >= 0 && i === htmlFlag + 1));
const [listFile, outDir] = pos;
if (!listFile || !outDir) {
  console.error('usage: render-music.mjs [--html <card.html>] [--viz[=tall]] <list> <outdir>');
  process.exit(1);
}

const tracks = fs.readFileSync(listFile, 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 640, height: 480 }, deviceScaleFactor: 2 });
await page.goto('file://' + path.resolve(htmlPath), { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);
if (viz) await page.evaluate(m => document.body.setAttribute('data-viz', m), vizMode);

let n = 0;
for (const stem of tracks) {
  const i = stem.indexOf(' - ');
  const artist = i > 0 ? stem.slice(0, i) : 'Unknown';
  const title = i > 0 ? stem.slice(i + 3) : stem;

  await page.evaluate(({ title, artist }) => {
    const t = document.getElementById('title');
    const a = document.getElementById('artist');
    t.textContent = title;
    a.textContent = artist;
    // shrink-to-fit: the title box must not reach the equaliser or the rule
    t.style.fontSize = '34px';
    for (let px = 34; px > 15 && t.getBoundingClientRect().height > 96; px -= 2) {
      t.style.fontSize = px + 'px';
    }
    a.style.fontSize = '16px';
    for (let px = 16; px > 10 && a.getBoundingClientRect().width > 400; px -= 1) {
      a.style.fontSize = px + 'px';
    }
  }, { title, artist });

  const safe = stem.replace(/[/:*?"<>|]/g, '');
  await page.screenshot({ path: path.join(outDir, safe + '.png'),
                          clip: { x: 0, y: 0, width: 640, height: 480 } });
  n++;
}

await browser.close();
console.log('rendered ' + n + ' music cards' + (viz ? ' (viz backplates, mode ' + vizMode + ')' : ''));
