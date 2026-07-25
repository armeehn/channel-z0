# vps/peertube/ — the tower, PeerTube edition

A **drop-in alternative to the Owncast tower** (`../docker-compose.yml`). Same
job — one RTMP stream in from home, HLS out to everyone — but PeerTube ships
**peer-to-peer (WebRTC) segment sharing on by default**, so viewers feed each
other and the VPS serves each segment far fewer times. On a linear channel,
where everyone is watching the same thing at the same playhead, that swarm is
about as good as P2P gets.

Pick **one** tower. Use this if your audience is big enough that egress is the
bill (P2P only helps once several people watch at once); stay on Owncast if it
isn't — Owncast is a single binary and this is a real stack.

| File | Goes where | Purpose |
|---|---|---|
| `docker-compose.yml` | `/opt/peertube/` | PeerTube + Postgres + Redis: RTMP in (1935), HLS out (9000) |
| `.env.example` | `/opt/peertube/.env` | DB creds, secret, hostname, admin email |

## What you trade vs Owncast

| | Owncast (`../`) | PeerTube (here) |
|---|---|---|
| Moving parts | one Go binary | app + **Postgres + Redis** |
| RAM (live-only) | a few hundred MB | ~2 GB realistic |
| P2P offload | added on the **site** side ([`site/index.html`](../../site/index.html)) | **built into its own player** |
| The catch | none, really | stateful deps to back up + upgrade; keep transcoding OFF |

> **You may not need this at all.** The Owncast tower + the P2P you already have
> in `site/index.html` (the `P2P_*` config) gets you swarm offload *without*
> Postgres/Redis. This directory is for when you'd rather the tower own the P2P
> and the player, chat, and accounts that come with PeerTube.

## Setup (VPS)

```bash
sudo mkdir -p /opt/peertube && cd /opt/peertube
# copy docker-compose.yml + .env.example here, then:
cp .env.example .env          # fill in a real DB password + PEERTUBE_SECRET
docker compose up -d
docker compose logs peertube | grep -A1 "Admin password"   # grab the one-time root password
```

Then, in the admin UI at `https://<your watch host>`:

1. **Log in** as `root` with that password; change it.
2. **Administration → Configuration → Live streaming → Enable live.**
3. **Turn live transcoding OFF.** This is the money setting: with it off,
   PeerTube just remuxes the incoming RTMP into HLS (cheap, single-resolution,
   exactly like Owncast). With it on, ffmpeg re-encodes per resolution per
   stream and can eat several CPU cores — the opposite of why you're here.
4. Confirm P2P is on: it is by default (**Administration → Configuration →
   Advanced** keeps the tracker enabled — "if you disable the tracker, you
   disable P2P").

## Caddy

Same pattern as the Owncast tower — Caddy terminates TLS and proxies to the
local port (9000 here instead of 8080). Put this alongside the block in
[`../Caddyfile`](../Caddyfile):

```caddy
watch.ch0.ripostelabs.xyz {
    reverse_proxy 127.0.0.1:9000
}
```

Then `sudo systemctl reload caddy`. (PeerTube serves the client + HLS itself, so
unlike the Owncast block you don't need the CORS header — the site embeds
PeerTube's own player in an iframe, not a cross-origin `fetch`.)

## Point the uplink at it — nothing in `playout/` changes

PeerTube's RTMP target has the **same shape** the uplink already pushes,
`rtmp://<host>:1935/live/<stream-key>`, so the [uplink](../../playout/compose.yml)
and [`.env`](../../.env.example) are untouched — only the **value** of
`Z0_STREAM_KEY` changes to PeerTube's key:

1. In the UI, **Publish → Go live → make it a *permanent/recurring* live** (so
   the key is stable across sessions instead of one-shot).
2. The **"Live settings"** tab shows the **RTMP URL** and the **stream key**.
3. Put that key in `Z0_STREAM_KEY` and set `Z0_WATCH_DOMAIN` to this host. The
   uplink reconnects forever, same as before.

## Put it on the storefront

PeerTube's player already does P2P, so on the site you embed it rather than
running the custom hls.js player. In [`site/index.html`](../../site/index.html)'s
`CONFIG`, set one line:

```js
PEERTUBE_EMBED: "https://watch.ch0.ripostelabs.xyz/videos/embed/<video-uuid>?p2p=1&muted=1",
```

The `<video-uuid>` is in the permanent live's URL. Setting it swaps the Live
Feed section to PeerTube's iframe (with its built-in P2P + chat) and leaves the
program grid, dossier, and the rest of the page exactly as they are. Leave it
blank to keep the Owncast + P2P player.

## Caveats worth repeating

- **Back up Postgres.** Owncast's config was a folder; here your instance lives
  in a database. `./data/postgres` is the important volume.
- **Domain + HTTPS are mandatory** — WebRTC needs a secure context and the P2P
  tracker runs over `wss://`. Caddy handles the certificate.
- **Live transcoding OFF** unless you have CPU to burn (or offload it to a
  PeerTube "remote runner"). This is the one setting that separates "as cheap as
  Owncast" from "melting the VPS."
