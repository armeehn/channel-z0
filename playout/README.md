# playout/ — master control

Runs on the 24/7 machine at home. ErsatzTV turns the media library into a
linear channel; the uplink service carries it to the tower.

| File | Purpose |
|---|---|
| `ersatztv.sh` | Start ErsatzTV in docker (pick your hardware-encoder tag) |
| `z0-uplink.service` | systemd unit: ffmpeg `-c copy` relay, restarts forever |

Media library layout: run `tools/make-media-tree.sh` to create it, and see
`docs/build-guide.md` Phase 2 for the schedule/filler configuration.
