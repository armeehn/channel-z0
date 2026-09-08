# vps/ — the tower

Runs on the cheap server. One stream in, every viewer out.

| File | Goes where | Purpose |
|---|---|---|
| `docker-compose.yml` | `/opt/owncast/` | Owncast: RTMP in (1935), HLS out (8080) |
| `Caddyfile` | `/etc/caddy/Caddyfile` | HTTPS for the Owncast watch subdomain + CORS for the storefront |
| [`peertube/`](peertube/) | `/opt/peertube/` | **Alternative tower** — PeerTube with peer-to-peer (WebRTC) delivery built in; heavier, for when egress is the bill |

**Two ways to cut the tower's egress as the audience grows**, both P2P (viewers
feed each other over WebRTC): keep Owncast and enable the `P2P_*` block in
[`site/index.html`](../site/index.html), *or* swap the tower for
[`peertube/`](peertube/), which owns the P2P and the player itself. Pick one;
see [`peertube/README.md`](peertube/README.md) for the trade-offs.

The storefront is **not** served from here anymore — it lives on Cloudflare
Pages (`ch0.ripostelabs.xyz`), so the VPS carries only video and Caddy's only
job is to terminate TLS for the tower and hand the cross-origin page the CORS
header it needs to pull the stream. See [`vps/Caddyfile`](Caddyfile).

Setup order and hardening (change the default admin password + stream key
FIRST): see `docs/pdf/docs-build-guide.pdf`, Phase 1. If you run the now-playing bridge,
also create an access token at `/admin/access-tokens` with the *set stream
title* scope.
