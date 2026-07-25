# vps/ — the tower

Runs on the cheap server. One stream in, every viewer out.

| File | Goes where | Purpose |
|---|---|---|
| `docker-compose.yml` | `/opt/owncast/` | Owncast: RTMP in (1935), HLS out (8080) |
| `Caddyfile` | `/etc/caddy/Caddyfile` | HTTPS + serves `site/` at your apex domain |

Setup order and hardening (change the default admin password + stream key
FIRST): see `docs/build-guide.md`, Phase 1.
