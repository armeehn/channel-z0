// Render one Channel Z0 music card PNG per track.
//
// One browser, N screenshots — launching Chromium 73 times would dominate the
// runtime. Text is injected per track rather than templating 73 HTML files.
//
// Long titles are shrunk to fit rather than allowed to overflow: the card is
// 640x480 and some of these 78s have titles like "Crossing Over the Ferry" in
// one breath and a five-word subtitle in the next.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const listFile = process.argv[2];
const outDir = process.argv[3];
if (!listFile || !outDir) { console.error('usage: render-music.mjs <list> <outdir>'); process.exit(1); }

const tracks = fs.readFileSync(listFile, 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 640, height: 480 }, deviceScaleFactor: 2 });
await page.goto('file://' + path.resolve('/root/z0cards/music-card.html'), { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);

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
console.log('rendered ' + n + ' music cards');
