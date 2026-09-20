# playout/ — master control

Runs on the 24/7 machine at home (a mini PC, or a homelab box — see
[`docs/pdf/docs-self-hosting.pdf`](../docs/pdf/docs-self-hosting.pdf)). ErsatzTV turns the media
library into a linear channel; the uplink carries it to the tower; the
now-playing bridge tells the storefront what's on.

| File | Purpose |
|---|---|
| `compose.yml` | **The whole home side in one file** — ErsatzTV + uplink + (optional) now-playing bridge |
| `ersatztv.sh` | Start just ErsatzTV in docker (pick your hardware-encoder tag) |
| `nowplaying.py` | The live marquee: reads ErsatzTV's guide, writes the current program into Owncast's title |
| `graphics-elements/` | The on-air overlays — bug, weather card, up-next, crawl. Deploy to ErsatzTV’s `/config/templates/graphics-elements/` ([manual](../docs/pdf/docs-weather.pdf)) |
| `z0-tools-sync.sh` | Populates the node's `.z0tools/tools/` and `.z0tools/lists/` copies (what root's cron runs, and the manifest `z0-lists.py` applies) from Gitea main, and installs `z0-leader.sh` into the live playout dir — recreating the `uplink` service when it changed; cron 04:30 and by hand after a merge. Watched by the sentinel check `z0-tools-in-sync` |
| `z0-uplink.service` | Bare-metal alternative to the compose `uplink`: systemd ffmpeg `-c copy` relay |
| `z0-gpu-autosense` + `.service`/`.timer` | Every minute, a real 1 s h264_vaapi encode on each `/dev/dri` node; re-points `FFmpegProfile` at the first that passes (Iris Xe > RX 580 > libx264) and restarts ErsatzTV on a change. A probe *timeout* must repeat twice before a down-switch (a loaded host stalls `docker run`); an error switches at once. Install: copy to `/usr/local/sbin/` and `/etc/systemd/system/`, `systemctl enable --now z0-gpu-autosense.timer`. Log `.z0-station/gpu-autosense.log` |

## Quick start (containerized)

```bash
cp ../.env.example .env          # fill in real values
docker compose up -d             # ersatztv + uplink
docker compose --profile nowplaying up -d   # ...and the live marquee
```

The `uplink` service replaces `z0-uplink.service` — use whichever you prefer;
don't run both. Media library layout: run `tools/make-media-tree.sh` to create
it, and see `docs/pdf/docs-build-guide.pdf` Phase 2 for the schedule/filler configuration.

## Loudness

The library spans -13 LUFS (gramophone sides) to -70 LUFS (silent cards), with
programmes around -22 to -28 and idents near -50. FFmpeg profile 1 therefore
runs ffmpeg's `loudnorm=I=-16:TP=-1.5:LRA=11` on every item (ErsatzTV
`NormalizeLoudnessMode=LoudNorm`, `TargetLoudness=-16`, enabled 2026-09-15).
That is the same target `tools/normalize-ad.sh` clears spots to, so a file
that skipped the pass still airs at station level. The uplink is `-c copy`,
so what ErsatzTV emits is what the tower carries. A change to the profile
takes effect at the next item, no restart. The sentinel check
`z0-loudness-normalized` fails if the mode is ever switched off.
