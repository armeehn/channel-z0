#!/usr/bin/env python3
"""Render Channel Z0's station intervals — generative art, by the chunk.

This is Glitchsheet used as a library rather than as a studio. A clip is one
coherent *piece*: a single source generator, one palette and one treatment
stack, with the seed and a couple of parameters swept across its chunks. That
is Glitchsheet's own idea — a chain of typed ops, and a sweep over one
parameter of it — pointed at a television channel instead of a vinyl cutter.

Why chunks. The engine caps a source at 240 frames, and peak memory runs about
23 MB per frame at 640x480 — 96 frames is enough to OOM LXC 114's 2 GB. So the
unit of rendering is a 240-frame chunk at 320x240 (8 s at 30 fps, ~1.5 GB
peak), and clips are assembled from chunks downstream. 320x240 doubles to the
channel's 640x480 by an exact integer nearest-neighbour scale, which costs
nothing and keeps the block edges hard — the look this is going for anyway.

Randomisation is driven off each op's own declared `varies` list and parameter
schema, the same metadata the studio UI is generated from, so this cannot emit
a chain the engine would reject. Everything is seeded: the same --seed renders
the same intervals, byte for byte.

Runs on LXC 114 (the only box with both numpy and ffglitch). Writes chunk
files plus a manifest; tools/z0-assemble.sh turns those into broadcast clips.
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time

# Must be set before glitchd.store is imported — it reads DATA_DIR at import
# time and defaults to /var/lib/glitchsheet, which is *v1's* directory. Using
# our own tree also keeps this batch's PNGs out of the studio's 6 GB cache, so
# an overnight render cannot evict somebody's working project.
DATA_DIR = os.environ.setdefault("GLITCHSHEET_DATA", "/var/lib/z0gen/cache")
os.environ.setdefault("GLITCHSHEET_RACK", "/opt/glitchsheet2/rack")
sys.path.insert(0, "/opt/glitchsheet2")

from glitchd import graph, ops, store  # noqa: E402

FFGAC = "/opt/ffglitch/bin/ffgac"

# 320x240 doubles to 640x480 exactly, so the upscale is nearest-neighbour with
# no interpolation and the block edges stay hard.
#
# 120 frames is 4 s at 30 fps, and it is set by MEMORY, not by the engine's
# 240-frame cap. Measured on LXC 114 (2 GB, shared with the live studio):
# a bare source costs ~83 MB + 5.9 MB/frame at this size (120 fr = 767 MB,
# 180 fr = 1137 MB), and the treatment stack lands on top of that. The
# heaviest stack the recipe builder emits — the one carrying time.slitscan,
# which materialises two full float32 RGBA gathers — renders at 120 frames and
# is OOM-killed at 150. So 120 with a real stack, not 240 with a bare source.
WIDTH, HEIGHT, FPS, FRAMES = 320, 240, 30, 120

# The six generators that actually move. `gradient` and `solid` have no time
# term (they emit N identical frames) and `media` needs a file, so none of the
# three belong in a generative pool.
SOURCES = ["flow", "plasma", "moire", "rings", "truchet", "voronoi", "feedback"]

# `as-is` is the passthrough — it would leave the raw luma ramp, which reads as
# grey mush on air. `mono` is kept: it is genuinely good under the channel bug.
PALETTES = ["riposte", "acid", "neon", "mono", "sunset",
            "cyber", "pastel", "cmyk", "rust", "vhs"]

# Treatments, grouped so a clip can take one from each shelf without stacking
# two ops that fight for the same territory.
# The shelves below are curated for BITRATE as much as for looks. The channel
# encodes 640x480 at 1200 kbps, and the first pass of this generator produced
# wall-to-wall high-frequency chroma noise measuring ~8 Mbps as an intermediate
# — content that arrives on air as mud and starves everything around it. So the
# ops that manufacture per-pixel detail (pixel.noise, pixel.recompress,
# pixel.sort, pixel.slices, colour.dither) are deliberately absent, and the ops
# that create FLAT regions (posterize, bitcrush, blockquant) are favoured: they
# both compress well and read as designed rather than damaged.
FORM = ["geom.mirror", "geom.polar", "geom.tile", "geom.wave", "geom.transform"]
COLOUR = ["colour.hsv", "colour.posterize", "colour.channels"]
TEXTURE = ["pixel.scanlines", "pixel.bitcrush", "pixel.shift"]
# time.slitscan is excluded twice over: it is the memory hog that caps the
# chunk size, and it shreds smooth motion into per-row noise.
MOTION = ["time.echo", "time.stutter"]
# The codec ops are the ffglitch ones — the actual datamosh, and the reason
# this is Glitchsheet rather than a plasma generator. smear/sink/tail work on
# motion vectors, so they smear along motion and stay smooth; blockquant
# coarsens quantisation, which flattens detail and helps the encoder.
CODEC_SOFT = ["codec.smear", "codec.sink", "codec.tail", "codec.blockquant"]
# codec.storm and codec.bleed are deliberately NOT here. Measured on a clean
# posterized plasma base, both produce structureless static at ~8 Mbps — no
# form survives them, and on a 1200 kbps channel they arrive as grey mud.
# codec.freeze holds macroblocks instead of injecting noise, so it keeps the
# underlying image legible and is the one heavy op worth having.
CODEC_HARD = ["codec.freeze"]


def _param_spec(op_id):
    spec = ops.get(op_id)
    return {p["k"]: p for p in spec.get("params", [])}, spec.get("varies", [])


def random_params(rng, op_id, force=None, lo_frac=0.10, hi_frac=0.50):
    """Pick values for an op straight from its declared schema.

    Only the params the op lists in `varies` are randomised — that list is the
    op author's own statement of which knobs are worth turning, and it keeps
    this from randomising things like `keep_alpha` that are structural rather
    than expressive.

    The default window is the BOTTOM HALF of each range. Sampling 15–85% (the
    first attempt) put almost every op near its maximum, and these ops compose
    multiplicatively: four ops at 70% is not a strong look, it is an unwatchable
    one. Restraint per op is what leaves the stack legible.
    """
    params, varies = _param_spec(op_id)
    out = {}
    for k in varies:
        p = params.get(k)
        if not p:
            continue
        if p["type"] == "num":
            lo, hi, step = p["min"], p["max"], p.get("step", 1) or 1
            lo2 = lo + (hi - lo) * lo_frac
            hi2 = lo + (hi - lo) * hi_frac
            n = int(round((rng.uniform(lo2, hi2) - lo) / step))
            out[k] = min(hi, max(lo, lo + n * step))
        elif p["type"] == "enum" and p.get("options"):
            opts = [o if isinstance(o, str) else o.get("v") for o in p["options"]]
            opts = [o for o in opts if o is not None]
            if opts:
                out[k] = rng.choice(opts)
        elif p["type"] == "bool":
            out[k] = rng.random() < 0.5
    if force:
        out.update(force)
    return out


def build_recipe(rng):
    """One clip's fixed identity: source, palette and treatment stack.

    A station interval has to hold the screen for up to four minutes between
    programmes, so the target is hypnotic, not abrasive — slow fields, flat
    colour, and glitch used as punctuation. The probabilities are tuned to give
    a median stack of three ops; stacking five reliably produced noise.
    """
    src = rng.choice(SOURCES)
    pal = rng.choice(PALETTES)
    stack = []
    if rng.random() < 0.50:
        stack.append(rng.choice(FORM))
    # Posterize-heavy colour treatment is the single biggest win for both looks
    # and bitrate, so colour is the most likely shelf.
    if rng.random() < 0.75:
        stack.append(rng.choice(COLOUR))
    if rng.random() < 0.35:
        stack.append(rng.choice(TEXTURE))
    if rng.random() < 0.30:
        stack.append(rng.choice(MOTION))
    # Under half the clips carry a codec pass. Making it universal (the first
    # attempt) meant every piece was damaged and the pool had no dynamic range;
    # the clean pieces are what make the moshed ones land. It is also a bitrate
    # decision: a clean posterized field measures ~800 kb/s as an intermediate
    # and the same field after any codec op measures 3.5–7.6 Mbps, because
    # datamosh output is high-entropy by construction.
    if rng.random() < 0.45:
        stack.append(rng.choice(CODEC_SOFT))
    if rng.random() < 0.12:
        stack.append(rng.choice(CODEC_HARD))
    # A small blur last. This is a bitrate decision as much as an aesthetic
    # one: it rolls off exactly the high-frequency chroma detail that a
    # 1200 kbps encoder cannot carry, and costs almost nothing to render.
    stack.append("pixel.blur")
    return {"source": src, "palette": pal, "stack": stack}


def chain_for(rng, recipe, chunk_index, n_chunks):
    """The chain for one chunk. The recipe is fixed; the seed moves, and one
    swept parameter walks across the clip so it evolves instead of cutting
    between unrelated images."""
    src_id = "source." + recipe["source"]
    sp = random_params(rng, src_id)
    sp.update({"width": WIDTH, "height": HEIGHT, "frames": FRAMES, "fps": FPS,
               "palette": recipe["palette"], "seed": rng.randint(1, 999999)})
    chain = [{"op": src_id, "params": sp}]

    t = chunk_index / max(1, n_chunks - 1) if n_chunks > 1 else 0.0
    for op_id in recipe["stack"]:
        if op_id == "pixel.blur":
            # Fixed and gentle, and deliberately exempt from the sweep below:
            # this op is here to roll off chroma noise for the encoder, and a
            # swept radius would end the clip in soup.
            chain.append({"op": "pixel.blur",
                          "params": {"radius": 1, "sharpen": 0}})
            continue
        p = random_params(rng, op_id)
        params_spec, varies = _param_spec(op_id)
        # Walk the first numeric `varies` param across the clip, low to high.
        for k in varies:
            spec = params_spec.get(k)
            if spec and spec["type"] == "num":
                lo = spec["min"] + (spec["max"] - spec["min"]) * 0.12
                hi = spec["min"] + (spec["max"] - spec["min"]) * 0.55
                step = spec.get("step", 1) or 1
                v = lo + (hi - lo) * t
                n = int(round((v - spec["min"]) / step))
                p[k] = min(spec["max"], max(spec["min"], spec["min"] + n * step))
                break
        chain.append({"op": op_id, "params": p})
    return chain


def render_chunk_worker(chain, out_path):
    """Render one chunk in THIS process. Only ever called in --worker mode.

    libxvid rather than H.264 because LXC 114 has only ffglitch's ffgac, which
    has no libx264 at all. The bitrate is far above what the channel will ever
    carry, so the generational loss to the final encode is not visible.
    """
    res = graph.evaluate(chain)
    cdir = store.cache_path(res["hash"])
    p = subprocess.run(
        [FFGAC, "-hide_banner", "-loglevel", "error", "-y",
         "-framerate", str(FPS), "-i", os.path.join(cdir, "f_%05d.png"),
         "-c:v", "libxvid", "-b:v", "9000k", "-pix_fmt", "yuv420p", out_path],
        capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffgac failed: " + p.stderr[-600:])
    return res["hash"]


def render_chunk(chain, out_path):
    """Render one chunk in a FRESH subprocess.

    Not an over-abstraction: numpy does not return freed arrays to the OS, so
    evaluating several chains back to back in one interpreter stacks their
    peaks and the container's OOM killer takes the whole batch with it —
    exit 137, no traceback, no partial manifest. A subprocess per chunk makes
    the peak per chunk rather than per run, and turns an OOM into one lost
    chunk. The ~1 s interpreter start is worth that.
    """
    payload = json.dumps({"chain": chain, "out": out_path})
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker"],
                       input=payload, capture_output=True, text=True)
    if p.returncode != 0:
        tail = (p.stderr or "").strip().splitlines()
        why = tail[-1] if tail else ("killed (signal %d)" % -p.returncode
                                     if p.returncode < 0 else
                                     "exit %d" % p.returncode)
        if p.returncode in (137, -9):
            why = "OOM-killed"
        raise RuntimeError(why)
    return json.loads(p.stdout)["hash"]


def worker():
    """One chunk, one process, chain on stdin, result on stdout."""
    import resource
    from glitchd import clip as clipmod

    # The engine writes a 200 px JPEG thumbnail beside every cached frame, for
    # a studio filmstrip nobody is looking at here — 120 of them per node, on
    # every node of the chain. Measured at 14% of chunk render time. The cache
    # entries are still perfectly valid without them; the studio would just
    # regenerate them if it ever opened one of these nodes.
    _orig_save = clipmod.Clip.save
    clipmod.Clip.save = lambda self, d, thumbs=True: _orig_save(self, d,
                                                                thumbs=False)

    req = json.load(sys.stdin)
    store.init()
    ops.load_all()
    h = render_chunk_worker(req["chain"], req["out"])
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    json.dump({"hash": h, "peak_mb": round(peak)}, sys.stdout)
    return 0


def main():
    global FRAMES
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", type=int, default=36)
    ap.add_argument("--chunks", type=int, default=20, help="chunks per clip")
    ap.add_argument("--frames", type=int, default=FRAMES,
                    help="frames per chunk; raising this risks the OOM killer")
    ap.add_argument("--seed", type=int, default=20260813)
    ap.add_argument("--out", default="/var/lib/z0gen/chunks")
    ap.add_argument("--start", type=int, default=0, help="first clip index (resume)")
    args = ap.parse_args()
    FRAMES = args.frames

    store.init()
    ops.load_all()
    os.makedirs(args.out, exist_ok=True)

    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = {"clips": []}
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    done = {c["index"] for c in manifest["clips"]}

    t_start = time.time()
    for ci in range(args.start, args.clips):
        if ci in done:
            print("clip %02d already rendered, skipping" % ci, flush=True)
            continue
        rng = random.Random(args.seed + ci * 7919)
        recipe = build_recipe(rng)
        entry = {"index": ci, "recipe": recipe, "chunks": [], "chains": []}
        t0 = time.time()
        ok = True
        for j in range(args.chunks):
            name = "c%02d_%02d.avi" % (ci, j)
            path = os.path.join(args.out, name)
            chain = chain_for(rng, recipe, j, args.chunks)
            try:
                render_chunk(chain, path)
            except Exception as e:
                # One bad chunk must not lose the batch. Ops can legitimately
                # fail on some inputs (a matte on an opaque clip, a codec pass
                # on a frame it cannot damage) and the honest response is to
                # drop the chunk and carry on.
                print("  chunk %s FAILED: %s: %s" % (name, type(e).__name__, e),
                      flush=True)
                ok = False
                continue
            entry["chunks"].append(name)
            entry["chains"].append(chain)
        if not entry["chunks"]:
            print("clip %02d produced nothing, skipped" % ci, flush=True)
            continue
        manifest["clips"].append(entry)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=1)
        # Keep the private cache small; the PNGs have served their purpose the
        # moment the chunk is muxed.
        store.prune_cache(800 * 1024 * 1024)
        print("clip %02d  %-9s %-7s %-52s %d/%d chunks  %5.1fs%s"
              % (ci, recipe["source"], recipe["palette"],
                 " > ".join(o.split(".")[1] for o in recipe["stack"])[:52],
                 len(entry["chunks"]), args.chunks, time.time() - t0,
                 "" if ok else "  (partial)"), flush=True)

    print("\n%d clips in manifest, %.1f min total"
          % (len(manifest["clips"]), (time.time() - t_start) / 60.0))
    return 0


if __name__ == "__main__":
    if "--worker" in sys.argv:
        sys.exit(worker())
    sys.exit(main())
