# playout/ — master control

Runs on the 24/7 machine at home (a mini PC, or a homelab box — see
[`docs/self-hosting.md`](../docs/self-hosting.md)). ErsatzTV turns the media
library into a linear channel; the uplink carries it to the tower; the
now-playing bridge tells the storefront what's on.

| File | Purpose |
|---|---|
| `compose.yml` | **The whole home side in one file** — ErsatzTV + uplink + (optional) now-playing bridge |
| `ersatztv.sh` | Start just ErsatzTV in docker (pick your hardware-encoder tag) |
| `nowplaying.py` | The live marquee: reads ErsatzTV's guide, writes the current program into Owncast's title |
| `z0-uplink.service` | Bare-metal alternative to the compose `uplink`: systemd ffmpeg `-c copy` relay |

## Quick start (containerized)

```bash
cp ../.env.example .env          # fill in real values
docker compose up -d             # ersatztv + uplink
docker compose --profile nowplaying up -d   # ...and the live marquee
```

The `uplink` service replaces `z0-uplink.service` — use whichever you prefer;
don't run both. Media library layout: run `tools/make-media-tree.sh` to create
it, and see `docs/build-guide.md` Phase 2 for the schedule/filler configuration.
