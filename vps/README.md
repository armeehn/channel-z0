# vps/ — the tower

Runs on the cheap server. One stream in, every viewer out.

| File | Goes where | Purpose |
|---|---|---|
| `docker-compose.yml` | `/opt/owncast/` | Owncast: RTMP in (1935), HLS out (8080) |
| `Caddyfile` | `/etc/caddy/Caddyfile` | HTTPS for the Owncast watch subdomain + CORS for the storefront |

The storefront is **not** served from here anymore — it lives on Cloudflare
Pages (`ch0.ripostelabs.xyz`), so the VPS carries only video and Caddy's only
job is to terminate TLS for the tower and hand the cross-origin page the CORS
header it needs to pull the stream. See [`vps/Caddyfile`](Caddyfile).

Setup order and hardening (change the default admin password + stream key
FIRST): see `docs/build-guide.md`, Phase 1. If you run the now-playing bridge,
also create an access token at `/admin/access-tokens` with the *set stream
title* scope.
