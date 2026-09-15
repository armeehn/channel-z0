#!/usr/bin/env python3
"""Channel Z0 — house promos: the merch and the projects, as 15–18 s spots.

The commercials slot in every advert break was empty (commercials/lab and
commercials/local never got a file). These fill it with the only adverts the
station runs: its own. Two kinds, two folders, two collections
(lists/z0-lists.yml):

    promos/merch/     one spot per live product on shop.ripostelabs.xyz
    promos/projects/  one spot per programme on api.hq (/v1/projects,
                      /v1/software) plus tools/z0-promos-extra.yml for
                      anything public that the API does not list yet

    z0-promos.py fetch  --feed DIR                     # on x: store + API → DIR
    z0-promos.py render --feed DIR --out DIR [--kind merch|projects|all]
                        [--extra z0-promos-extra.yml] [--seed N] [--jobs J]

`fetch` runs where the store and api.hq are reachable (x); `render` runs where
numpy is (forge). The feed is a directory: products.json, projects.json,
software.json, images/<handle>.png. A spot is deterministic in its handle, so
a refresh re-renders only what changed and the folder is a mirror of the feed
— the shipper syncs promos/ with --delete, unlike bumps/ which only grows.

Backgrounds come from z0_bumps (same directory): a calm genre, dimmed, with
the product or the programme on top. Same house spec, same NFO shape, same
standing constraints (no crosshairs, nothing over the gutters).
"""

import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
np = Image = ImageDraw = zb = None


def _load_engine():
    """numpy, PIL and the engine are only needed to render. `fetch` runs on x,
    which has neither, so the imports are deferred."""
    global np, Image, ImageDraw, zb
    if zb is not None:
        return
    import numpy
    from PIL import Image as _Image, ImageDraw as _ImageDraw
    spec = importlib.util.spec_from_file_location("z0_bumps", os.path.join(HERE, "z0_bumps.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    np, Image, ImageDraw, zb = numpy, _Image, _ImageDraw, mod

SHOP_URL = "https://shop.ripostelabs.xyz"
API_URL = "https://api.hq.ripostelabs.xyz/v1"
MERCH_SECS = 15
PROJECT_SECS = 18
FRAME_W = 854
SAFE_X0, SAFE_X1 = 128, FRAME_W - 128      # inside the 107 px rails, with air
CURRENCY = "CA$"

# Calm genres that read as a field, not a subject, under text.
MERCH_BACKGROUNDS = ["flow", "moire", "chladni", "ripple", "voronoi", "truchet",
                     "phyllotaxis", "lorenz", "attractor", "harmonograph"]
PROJECT_BACKGROUNDS = {
    "hex": "hexgrid", "spool": "spiro", "plastic-works": "voronoi",
    "cutsheet": "truchet", "glitchsheet": "julia", "bean": "automaton",
    "daily-bread": "ripple", "channel-z0": "moire", "riposte-brand": "chladni",
}
PROJECT_TREATMENT = {"glitchsheet": "bleed"}
MERCH_LINES = [
    "everything here is free. the shirts are not.",
    "recycled blanks. printed in house.",
    "wear the channel.",
    "the only ads are ours.",
]


# ══ Feed ═════════════════════════════════════════════════════════════════════

def fetch(feed_dir):
    os.makedirs(os.path.join(feed_dir, "images"), exist_ok=True)

    def get(url, out):
        req = urllib.request.Request(url, headers={"User-Agent": "z0-promos/1"})
        with urllib.request.urlopen(req, timeout=30) as r, open(out, "wb") as fh:
            fh.write(r.read())

    get(SHOP_URL + "/products.json?limit=250", os.path.join(feed_dir, "products.json"))
    get(API_URL + "/projects", os.path.join(feed_dir, "projects.json"))
    get(API_URL + "/software", os.path.join(feed_dir, "software.json"))
    with open(os.path.join(feed_dir, "products.json"), encoding="utf-8") as fh:
        products = json.load(fh)["products"]
    n = 0
    for p in products:
        if not p.get("images"):
            continue
        out = os.path.join(feed_dir, "images", p["handle"] + ".png")
        if os.path.exists(out):
            continue
        get(p["images"][0]["src"].split("?")[0], out)
        n += 1
    print(f"feed: {len(products)} products, {n} new images → {feed_dir}")


def load_feed(feed_dir, extra=None):
    def load(name):
        with open(os.path.join(feed_dir, name), encoding="utf-8") as fh:
            return json.load(fh)

    products = [p for p in load("products.json")["products"] if p.get("variants")]
    projects = load("projects.json").get("projects", [])
    software = load("software.json").get("software", [])
    entries = []
    for p in projects:
        entries.append(dict(id=p["id"], doc_no=p.get("doc_no", ""), name=p["name"],
                            subtitle=p.get("subtitle", ""), status=p.get("status", ""),
                            summary=p.get("summary", "")))
    for s in software:
        entries.append(dict(id=s["id"], doc_no="", name=s["name"], subtitle=s.get("kind", ""),
                            status="", summary=s.get("summary", "")))
    if extra and os.path.exists(extra):
        import yaml
        with open(extra, encoding="utf-8") as fh:
            for e in (yaml.safe_load(fh) or {}).get("projects", []):
                entries.append(dict(id=e["id"], doc_no=e.get("doc_no", ""), name=e["name"],
                                    subtitle=e.get("subtitle", ""), status=e.get("status", ""),
                                    summary=e.get("summary", ""), genre=e.get("genre")))
    return products, entries


def stable_seed(key, salt):
    h = hashlib.sha1(f"{salt}:{key}".encode()).hexdigest()
    return int(h[:8], 16) % 100000


def price_of(product):
    prices = sorted(float(v["price"]) for v in product["variants"] if v.get("price"))
    if not prices:
        return ""
    lo = prices[0]
    txt = f"{CURRENCY}{lo:.0f}" if lo == int(lo) else f"{CURRENCY}{lo:.2f}"
    return txt if len(set(prices)) == 1 else "from " + txt


# ══ Drawing ══════════════════════════════════════════════════════════════════

def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def fit_lines(d, text, fonts, size, max_w, max_lines, min_size=16):
    font = fonts.at(size)
    lines = zb.wrap_text(d, text, font, max_w)
    while len(lines) > max_lines and size > min_size:
        size -= 2
        font = fonts.at(size)
        lines = zb.wrap_text(d, text, font, max_w)
    return lines, font, size


def dim(frame, k):
    return (frame.astype(np.float32) * k).astype(np.uint8)


def merch_overlay(bg, product, photo, fonts, t, secs):
    """The product panel slides in from the right; the copy fades in on the
    left. Everything sits inside the rail-safe columns."""
    img = Image.fromarray(bg)
    d = ImageDraw.Draw(img)
    # Photo panel: 300 px square, bone frame, ink hairline.
    ps = 300
    px_final = SAFE_X1 - ps
    py = (zb.H - ps) // 2 - 10
    slide = ease_out((t - 0.1) / 0.7)
    px = int(px_final + (1 - slide) * 160)
    bob = int(3 * np.sin(2 * np.pi * 0.5 * t))
    d.rectangle((px - 6, py - 6 + bob, px + ps + 6, py + ps + 6 + bob), fill=zb.BONE)
    img.paste(photo, (px, py + bob))
    d.rectangle((px, py + bob, px + ps - 1, py + ps - 1 + bob), outline=zb.INK, width=1)
    # Copy column.
    cx = SAFE_X0
    col_w = px_final - 28 - cx
    a_eyebrow = zb.smoothstep(0.3, 0.7, np.array([t]))[0]
    a_title = zb.smoothstep(0.6, 1.1, np.array([t]))[0]
    a_price = zb.smoothstep(1.2, 1.6, np.array([t]))[0]
    a_line = zb.smoothstep(1.7, 2.2, np.array([t]))[0]
    over = Image.new("RGB", img.size, (0, 0, 0))
    od = ImageDraw.Draw(over)
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)

    def text(xy, s, font, fill, alpha):
        od.text(xy, s, font=font, fill=fill)
        md.text(xy, s, font=font, fill=int(255 * alpha))

    y = 118
    f_eye = fonts.at(16)
    text((cx, y), "MERCH · SHOP.RIPOSTELABS.XYZ", f_eye, zb.MARIGOLD, a_eyebrow)
    y += 34
    lines, f_title, size = fit_lines(d, product["title"], fonts, 30, col_w, 3, 20)
    for line in lines:
        text((cx, y), line, f_title, zb.BONE, a_title)
        y += size + 8
    y += 10
    text((cx, y), price_of(product), fonts.at(30), zb.BONE, a_price)
    y += 48
    small, f_small, ssize = fit_lines(d, "recycled blanks. printed in house.", fonts, 16, col_w, 3, 14)
    for line in small:
        text((cx, y), line, f_small, zb.BONE_DIM, a_line)
        y += ssize + 6
    img.paste(over, (0, 0), mask)
    return np.asarray(img)


def project_overlay(bg, entry, fonts, t, secs):
    """Badge, then the name typed out, then the subtitle and the summary."""
    img = Image.fromarray(bg)
    d = ImageDraw.Draw(img)
    over = Image.new("RGB", img.size, (0, 0, 0))
    od = ImageDraw.Draw(over)
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)

    def text(xy, s, font, fill, alpha):
        od.text(xy, s, font=font, fill=fill)
        md.text(xy, s, font=font, fill=int(255 * alpha))

    col_w = SAFE_X1 - SAFE_X0
    x = SAFE_X0
    y = 92
    # Badge: doc number and status, marigold on ink.
    badge = " · ".join(b for b in (entry.get("doc_no", ""), entry.get("status", "").upper()) if b)
    if badge:
        a = zb.smoothstep(0.3, 0.7, np.array([t]))[0]
        f = fonts.at(16)
        bw = d.textlength(badge, font=f)
        od.rectangle((x - 8, y - 6, x + bw + 8, y + 22), fill=zb.INK)
        md.rectangle((x - 8, y - 6, x + bw + 8, y + 22), fill=int(255 * a))
        od.rectangle((x - 8, y - 6, x - 4, y + 22), fill=zb.MARIGOLD)
        text((x, y), badge, f, zb.MARIGOLD, a)
    y += 46
    # Name, typed.
    lines, f_name, size = fit_lines(d, entry["name"], fonts, 44, col_w, 2, 28)
    full = " ".join(lines)
    shown = int(max(0.0, t - 0.8) * 14)
    typed = full[:shown]
    cursor = "_" if (shown < len(full) and int(t * 3) % 2 == 0) else ""
    remaining = typed
    for line in lines:
        seg = remaining[:len(line)]
        remaining = remaining[len(line) + 1:]
        if seg:
            text((x, y), seg + (cursor if not remaining and shown < len(full) else ""), f_name, zb.BONE, 1.0)
        y += size + 8
    done_at = 0.8 + len(full) / 14
    y += 6
    if entry.get("subtitle"):
        a = zb.smoothstep(done_at + 0.2, done_at + 0.6, np.array([t]))[0]
        text((x, y), entry["subtitle"].lower(), fonts.at(22), zb.MARIGOLD, a)
    y += 44
    lines, f_sum, size = fit_lines(d, entry.get("summary", ""), fonts, 18, col_w, 5, 15)
    for k, line in enumerate(lines):
        a = zb.smoothstep(done_at + 0.8 + 0.25 * k, done_at + 1.2 + 0.25 * k, np.array([t]))[0]
        text((x, y), line, f_sum, zb.BONE_DIM, a)
        y += size + 8
    a = zb.smoothstep(done_at + 2.2, done_at + 2.7, np.array([t]))[0]
    text((x, zb.H - 84), "RIPOSTELABS.XYZ", fonts.at(16), zb.TEAL, a)
    img.paste(over, (0, 0), mask)
    return np.asarray(img)


def promo_card(big, small, fonts, eyebrow):
    img = Image.new("RGB", (zb.W, zb.H), zb.INK)
    d = ImageDraw.Draw(img)
    f_big = fonts.at(38)
    lines = zb.wrap_text(d, big, f_big, zb.W - 260)
    lh = 50
    block = lh * len(lines) + 40
    y0 = (zb.H - block) // 2
    f_eye = fonts.at(16)
    ew = d.textlength(eyebrow, font=f_eye)
    d.text(((zb.W - ew) / 2, y0 - 30), eyebrow, font=f_eye, fill=zb.MARIGOLD)
    d.rectangle((150, y0 - 44, zb.W - 150, y0 - 41), fill=zb.BONE)
    for k, line in enumerate(lines):
        tw = d.textlength(line, font=f_big)
        d.text(((zb.W - tw) / 2, y0 + k * lh), line, font=f_big, fill=zb.BONE)
    f_small = fonts.at(20)
    sw = d.textlength(small, font=f_small)
    d.text(((zb.W - sw) / 2, y0 + lh * len(lines) + 4), small, font=f_small, fill=zb.BONE_DIM)
    d.rectangle((150, y0 + block + 8, zb.W - 150, y0 + block + 11), fill=zb.BONE)
    zb.draw_wordmark(d, fonts, zb.W - 132, zb.H - 58)
    d.text((132, zb.H - 54), "CH 0 · A LOCAL CHANNEL, FOR LOCALS", font=fonts.at(16), fill=zb.INK_LINE)
    return np.asarray(img)


# ══ One spot ═════════════════════════════════════════════════════════════════

def render_spot(spec):
    kind = spec["kind"]
    seed = spec["seed"]
    secs = spec["secs"]
    rng = np.random.default_rng(seed)
    fonts = zb.Fonts(spec.get("font"))
    art_secs = secs - zb.CARD_SECS
    n_total = int(round(secs * zb.FPS))
    n_art = int(round(art_secs * zb.FPS))
    out_dir = spec["out_dir"]
    os.makedirs(out_dir, exist_ok=True)

    if kind == "merch":
        product = spec["product"]
        clip_id = "z0-promo-merch-" + product["handle"]
        genre_name = str(rng.choice(MERCH_BACKGROUNDS))
        photo = Image.open(spec["image"]).convert("RGB").resize((300, 300), Image.LANCZOS)
        card = promo_card("shop.ripostelabs.xyz", str(rng.choice(MERCH_LINES)), fonts, "MERCH")
        outline = f"{product['title']} — {price_of(product)} — shop.ripostelabs.xyz"
        tags = ["media", "promos", "station-furniture", "promo-merch", product["handle"]]
        treatment = None
    else:
        entry = spec["entry"]
        clip_id = "z0-promo-project-" + entry["id"]
        genre_name = entry.get("genre") or PROJECT_BACKGROUNDS.get(entry["id"], "flow")
        photo = None
        card = promo_card(entry["name"], "ripostelabs.xyz", fonts, entry.get("subtitle", "").upper() or "RIPOSTE LABORATORIES")
        outline = f"{entry['name']}: {entry.get('subtitle', '')}. {entry.get('summary', '')}"
        tags = ["media", "promos", "station-furniture", "promo-projects", entry["id"]]
        t_name = PROJECT_TREATMENT.get(entry["id"])
        treatment = zb.TREATMENTS[t_name](rng) if t_name else None

    genre = zb.make_genre(genre_name, rng, art_secs + 1.0, font_path=fonts.path)
    env = zb.burst_envelope(rng, n_art, True) * 0.6 if treatment else None
    mp4 = os.path.join(out_dir, clip_id + ".mp4")
    nfo = os.path.join(out_dir, clip_id + ".nfo")
    wav = os.path.join(out_dir, "." + clip_id + ".wav")
    zb.write_wav(wav, zb.synth_audio(rng, secs, art_secs, None, "math"))
    proc = subprocess.Popen(zb.ffmpeg_cmd(mp4, wav), stdin=subprocess.PIPE)
    try:
        for i in range(n_total):
            t = i / zb.FPS
            if i < n_art:
                u = i / max(n_art - 1, 1)
                bg = np.ascontiguousarray(genre.frame(i, t, u))
                if treatment is not None:
                    bg = np.ascontiguousarray(treatment.apply(bg, float(env[i]), i, t))
                bg = dim(bg, 0.42)
                if kind == "merch":
                    fr = merch_overlay(bg, product, photo, fonts, t, secs)
                else:
                    fr = project_overlay(bg, entry, fonts, t, secs)
            else:
                fr = card
                remaining = secs - t
                if remaining < zb.CARD_FADE:
                    fr = dim(fr, remaining / zb.CARD_FADE)
            proc.stdin.write(np.ascontiguousarray(fr, dtype=np.uint8).tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
        if os.path.exists(wav):
            os.remove(wav)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}) for {clip_id}")
    with open(nfo, "w", encoding="utf-8") as fh:
        fh.write(zb.nfo_xml(clip_id, outline, tags))
    return {"id": clip_id, "kind": kind, "genre": genre_name, "seed": seed, "secs": secs,
            "bytes": os.path.getsize(mp4)}


def _worker(spec):
    _load_engine()
    try:
        return ("ok", render_spot(spec))
    except Exception as exc:
        return ("err", {"id": spec.get("kind", "?"), "error": repr(exc)})


# ══ CLI ══════════════════════════════════════════════════════════════════════

def cmd_fetch(args):
    fetch(args.feed)


def cmd_render(args):
    _load_engine()
    font = zb.find_font(args.font)
    products, entries = load_feed(args.feed, args.extra)
    specs = []
    if args.kind in ("merch", "all"):
        for p in products:
            image = os.path.join(args.feed, "images", p["handle"] + ".png")
            if not os.path.exists(image):
                print(f"skip {p['handle']}: no image in feed", file=sys.stderr)
                continue
            specs.append(dict(kind="merch", product=p, image=image, font=font,
                              seed=stable_seed(p["handle"], args.seed), secs=args.merch_secs,
                              out_dir=os.path.join(args.out, "merch")))
    if args.kind in ("projects", "all"):
        for e in entries:
            specs.append(dict(kind="projects", entry=e, font=font,
                              seed=stable_seed(e["id"], args.seed), secs=args.project_secs,
                              out_dir=os.path.join(args.out, "projects")))
    if args.only:
        specs = [s for s in specs if args.only in (s.get("product", {}).get("handle"), s.get("entry", {}).get("id"))]
    jobs = args.jobs or max(1, min(len(specs), os.cpu_count() or 1))
    os.makedirs(args.out, exist_ok=True)
    ok = err = 0
    with mp.Pool(jobs) as pool, open(os.path.join(args.out, "manifest.jsonl"), "a", encoding="utf-8") as mf:
        for status, row in pool.imap_unordered(_worker, specs):
            if status == "ok":
                ok += 1
                mf.write(json.dumps(row) + "\n")
                print(f"ok   {row['id']}  {row['bytes'] * 8 / row['secs'] / 1000:5.0f} kbps  bg={row['genre']}")
            else:
                err += 1
                print(f"FAIL {row['id']}  {row['error']}", file=sys.stderr)
    print(f"{ok} rendered, {err} failed → {args.out}")
    return 1 if err else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--feed", required=True)
    f.set_defaults(fn=cmd_fetch)
    r = sub.add_parser("render")
    r.add_argument("--feed", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--kind", choices=["merch", "projects", "all"], default="all")
    r.add_argument("--extra", default=os.path.join(HERE, "z0-promos-extra.yml"))
    r.add_argument("--only", help="one product handle or project id")
    r.add_argument("--seed", type=int, default=1, help="salt: same salt, same spots")
    r.add_argument("--merch-secs", type=float, default=MERCH_SECS)
    r.add_argument("--project-secs", type=float, default=PROJECT_SECS)
    r.add_argument("--jobs", type=int)
    r.add_argument("--font")
    r.set_defaults(fn=cmd_render)
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
