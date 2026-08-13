#!/usr/bin/env python3
"""Assemble rendered chunks into broadcast-ready station intervals.

tools/z0-generative.py emits 4-second chunks at 320x240, because that is what
LXC 114's memory allows. This turns each clip's run of chunks into one file the
channel can play: crossfaded so the piece evolves instead of cutting, doubled
to 640x480, and given the silent audio track ErsatzTV expects.

Runs anywhere with ffmpeg + libx264 — in practice LXC 111, which is idle and,
unlike vile, is not also running the live transcode at a 5% realtime margin.

Two deliberate choices worth knowing:

  * The upscale is `flags=neighbor`, an exact 2x integer nearest-neighbour
    scale. Bicubic would smooth away the block edges that the codec ops exist
    to create, and it is those hard edges that read as glitch rather than blur.

  * The audio is silent. The channel's own colour bars and test card are silent
    too (tools/make-colorbars.sh feeds anullsrc), so this matches the station,
    and four minutes of tone between programmes would wear badly. It is a real
    stereo 48 kHz AAC track, not a missing one — ErsatzTV normalises audio and
    a stream that is simply absent is a needless edge case.
"""

import argparse
import json
import os
import random
import subprocess
import sys

# Transitions available in every ffmpeg since 4.3. Deliberately a short list:
# the wilder xfade transitions (squeeze, hlwind, and the like) read as
# presentation-software wipes and fight the material.
TRANSITIONS = ["fade", "dissolve", "pixelize", "radial", "circleopen",
               "wipeleft", "smoothleft"]


def probe_duration(path, ffprobe):
    p = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return -1.0


def build_cmd(chunks, out, args, rng):
    """One ffmpeg invocation: N chunks in, one interval out.

    The xfade offsets are cumulative. Each chunk contributes (chunk - xfade)
    seconds of new material after the first, so offset_i = (i+1)*(L-D) and the
    finished piece is L + (N-1)*(L-D) seconds long.
    """
    step = args.chunk - args.xfade
    cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for c in chunks:
        cmd += ["-i", c]
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]

    parts = []
    for i in range(len(chunks)):
        parts.append("[%d:v]settb=AVTB,fps=%d,format=yuv420p,"
                     "setpts=PTS-STARTPTS[p%d]" % (i, args.fps, i))

    if len(chunks) == 1:
        last = "p0"
    else:
        last = "p0"
        for i in range(1, len(chunks)):
            tag = "x%d" % i
            parts.append("[%s][p%d]xfade=transition=%s:duration=%g:offset=%g[%s]"
                         % (last, i, rng.choice(TRANSITIONS), args.xfade,
                            step * i, tag))
            last = tag

    # Upscale once, at the end, after every crossfade has been done at the
    # cheaper size.
    parts.append("[%s]scale=%d:%d:flags=neighbor,setsar=1,format=yuv420p[v]"
                 % (last, args.width, args.height))

    cmd += ["-filter_complex", ";".join(parts),
            "-map", "[v]", "-map", "%d:a" % len(chunks), "-shortest",
            "-c:v", "libx264", "-preset", args.preset, "-b:v", args.bitrate,
            "-pix_fmt", "yuv420p", "-r", str(args.fps),
            "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", out]
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks-dir", default="/tmp/z0gen/chunks")
    ap.add_argument("--out-dir", default="/tmp/z0gen/intervals")
    ap.add_argument("--chunk", type=float, default=4.0, help="chunk seconds")
    ap.add_argument("--xfade", type=float, default=1.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--bitrate", default="3000k")
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--seed", type=int, default=20260813)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    args = ap.parse_args()

    with open(os.path.join(args.chunks_dir, "manifest.json")) as f:
        manifest = json.load(f)
    os.makedirs(args.out_dir, exist_ok=True)

    expected = args.chunk
    made, failed = 0, 0
    index = []
    for clip in manifest["clips"]:
        ci = clip["index"]
        chunks = [os.path.join(args.chunks_dir, c) for c in clip["chunks"]]
        chunks = [c for c in chunks if os.path.exists(c)]
        if not chunks:
            continue
        want = args.chunk + (len(chunks) - 1) * (args.chunk - args.xfade)
        name = "z0-interval-%02d.mp4" % ci
        out = os.path.join(args.out_dir, name)
        # The temp name has to keep the .mp4 extension: ffmpeg picks the muxer
        # from it, and a trailing .tmp gets "Unable to choose an output format".
        tmp = os.path.join(args.out_dir, ".%s.tmp.mp4" % name[:-4])
        rng = random.Random(args.seed + ci)

        p = subprocess.run(build_cmd(chunks, tmp, args, rng),
                           capture_output=True, text=True)
        if p.returncode != 0:
            print("clip %02d FAILED: %s" % (ci, p.stderr.strip()[-400:]))
            failed += 1
            continue

        # A length guard, in the spirit of tools/z0-weather.sh: a file that is
        # not the length the schedule was planned around is worse than no file,
        # because nothing downstream reports it.
        dur = probe_duration(tmp, args.ffprobe)
        if abs(dur - want) > 1.0:
            print("clip %02d REFUSED: %.2fs, expected %.2fs" % (ci, dur, want))
            os.unlink(tmp)
            failed += 1
            continue

        os.replace(tmp, out)   # atomic within the directory
        size = os.path.getsize(out) / 1048576.0
        r = clip["recipe"]
        print("%-22s %6.1fs %5.1f MiB  %-9s %-7s %s"
              % (name, dur, size, r["source"], r["palette"],
                 " > ".join(o.split(".")[1] for o in r["stack"])[:44]))
        index.append({"file": name, "seconds": round(dur, 2),
                      "recipe": r, "chunks": len(chunks)})
        made += 1

    with open(os.path.join(args.out_dir, "intervals.json"), "w") as f:
        json.dump({"intervals": index}, f, indent=1)
    total = sum(i["seconds"] for i in index)
    print("\n%d intervals, %d failed, %.1f min of material"
          % (made, failed, total / 60.0))
    return 1 if made == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
