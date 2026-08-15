# CHANNEL Z0

```
┌───────────────────────────────────────────────┐
│   CHANNEL Z0 · CH 0 · DESIG RL-Z0             │
│   a local channel, for locals                 │
│   a Riposte Laboratories transmission         │
└───────────────────────────────────────────────┘
```

An old-style TV channel built on new plumbing: one linear channel that runs
24/7 from a machine in a house, with scheduled shows, locally submitted
commercials, station bumpers, a nightly flagship (**GROUND ZERO** — alien
street interviews conducted via baguette), and a midnight sign-off to colour
bars, exactly as civilization intended.

This repository is the whole station: the playout configuration, the uplink,
the tower, the storefront website, and the operating manual.

## How it works

```
 YOUR HOUSE (10 Mbps+ up)              CHEAP VPS ($0–8/mo)              EVERYONE ELSE
┌─────────────────────────┐          ┌──────────────────────┐        ┌──────────────┐
│  Playout PC (24/7)      │          │  Owncast             │        │ Browsers     │
│  ┌───────────────────┐  │  ONE     │  ┌────────────────┐  │  HLS   │ Phones       │
│  │ ErsatzTV          │  │  STREAM  │  │ RTMP in :1935  │──┼──────▶│ Smart TVs    │
│  │ (schedules, ads,  │──┼────────▶│  │ HLS out :8080  │  │        │ Someone's    │
│  │  filler, bug)     │  │  RTMP    │  └────────────────┘  │        │ house, all   │
│  └───────────────────┘  │  ~5 Mbps │  + Caddy (HTTPS)     │        │ day long     │
│  + OBS for live shows   │          │  + the storefront    │        └──────────────┘
└─────────────────────────┘          └──────────────────────┘
```

**Exactly one stream ever leaves the house.** The VPS does the crowd work, so
a residential connection can run a channel with an unlimited audience. Latency
is ~20 seconds and that is fine, because this is television, not a phone call.

## Repository map

| Path | What it is |
|---|---|
| [`docs/build-guide.md`](docs/build-guide.md) | **Start here.** The full station build, Phase 0 → on-air |
| [`docs/programming.md`](docs/programming.md) | **The broadcast week.** The full schedule, the show bible, and the ErsatzTV mapping |
| [`docs/archive-fetch.md`](docs/archive-fetch.md) | **Stocking the library.** Public-domain intake from the Internet Archive |
| [`docs/clustering.md`](docs/clustering.md) | **More than one machine.** Node roles, failover, and what can't be load-balanced |
| [`docs/self-hosting.md`](docs/self-hosting.md) | Run master control on a homelab — Proxmox & TrueNAS, GPU passthrough, tips |
| [`docs/gear-and-costs.md`](docs/gear-and-costs.md) | Hardware picks, VPS comparison, bandwidth math, budgets |
| [`docs/weather.md`](docs/weather.md) | **On-air graphics.** The bug, the weather desk, the crawl, and the traps in ErsatzTV’s graphics engine |
| [`docs/ad-standards.md`](docs/ad-standards.md) | The one-page rulebook for locally submitted commercials |
| [`docs/ideas.md`](docs/ideas.md) | The writers' room — what's shipped, what's next |
| [`site/index.html`](site/index.html) | The storefront — live player (pause, volume, full screen), program grid, ad submissions (Riposte Labs design language) |
| [`site/retro/index.html`](site/retro/index.html) | The original CRT-and-wood-cabinet version, preserved |
| [`site/_headers`](site/_headers) · [`site/_redirects`](site/_redirects) | Cloudflare headers + short links (`/watch`, `/lab`) |
| [`vps/`](vps/) | The tower: Owncast `docker-compose.yml` + `Caddyfile` (and [`vps/peertube/`](vps/peertube/) — a peer-to-peer alternative tower) |
| [`playout/`](playout/) | Master control: `compose.yml` (containerized), ErsatzTV launcher, uplink supervisor, now-playing bridge |
| [`tools/`](tools/) | Station scripts — see below |
| [`wrangler.jsonc`](wrangler.jsonc) | Cloudflare Worker config (serves `site/` as static assets at `ch0.ripostelabs.xyz`) |
| [`.env.example`](.env.example) | Domains, stream key, media root, tokens — copy, fill, never commit |

### Station scripts

| Script | Job |
|---|---|
| `tools/bootstrap-node.sh` | Stand up a node from a bare machine — playout, tower, or worker ([manual](docs/clustering.md)) |
| `tools/make-media-tree.sh` | Create the media library layout on the playout PC |
| `tools/z0-weather.sh` | The weather desk — renders the corner card, the crawl and the forecast segment ([manual](docs/weather.md)) |
| `tools/wire-graphics.py` | Wires the graphics elements and forecast slots into the broadcast week ([manual](docs/weather.md)) |
| `tools/fetch-archive.sh` | Stock the library from archive.org — public domain only, resumable ([manual](docs/archive-fetch.md)) |
| `tools/make-proxies.sh` | Build a test library — tiny stand-ins with identical runtimes, for trying schedules |
| `tools/test-failover.sh` | Prove the cluster fails over and never double-publishes |
| `tools/test-generators.sh` | Prove the card generators still make cards — arguments, text, 1080p/30 conformance |
| `tools/test-broadcast.sh` | Fire a live test pattern at the tower (build guide, Phase 1.5) |
| `tools/test-player-controls.mjs` | Drive the storefront player in a real browser — pause/resume-at-live, mute + volume, full screen (needs the channel on air) |
| `tools/check-ad.sh` | Screen a submitted spot: length, codecs, true loudness (read-only) |
| `tools/normalize-ad.sh` | Clear a submitted spot for air: 1080p/30, loudness-normalized |
| `tools/make-colorbars.sh` | Generate the midnight sign-off bars (with optional silence) |
| `tools/make-testcard.sh` | Generate the station test card — the branded signal-check pattern with a 1 kHz line-up tone |
| `tools/make-signoff.sh` | Generate the nightly sign-off — the "broadcast day concludes" card dissolving into colour bars |
| `tools/make-ident.sh` | Generate station idents — the "NOW WATCHING CHANNEL Z0" bumpers |
| `tools/make-slate.sh` | Generate slate cards — technical difficulties, sign-off, please stand by |
| `tools/make-bug.sh` | Generate the channel bug (watermark PNG) for ErsatzTV |

## Quickstart

The short version — the [build guide](docs/build-guide.md) has every command.

1. **Phase 0 — names.** A domain, a VPS, two DNS records. See
   [gear-and-costs](docs/gear-and-costs.md) for picking the VPS (spoiler: it
   can be $0).
2. **Phase 1 — the tower.** On the VPS: `vps/docker-compose.yml` up, Caddy
   configured, then immediately change Owncast's default admin password and
   stream key. Prove the pipe with `tools/test-broadcast.sh`.
3. **Phase 2 — master control.** On the playout PC (or a homelab box — see
   [self-hosting](docs/self-hosting.md)): `tools/make-media-tree.sh`, fill the
   library (`tools/fetch-archive.sh --all` stocks the public-domain half —
   see [archive-fetch](docs/archive-fetch.md)), then either
   `playout/ersatztv.sh` or the whole containerized stack
   with `cd playout && docker compose up -d`. Build the schedule and ad-break
   filler in the ErsatzTV UI.
4. **Phase 3 — the uplink.** The `uplink` service in `playout/compose.yml`
   carries one stream to the tower and reconnects forever (or install the
   bare-metal `playout/z0-uplink.service`). Optionally add the now-playing
   bridge: `docker compose --profile nowplaying up -d`. You now run a
   television station.
5. **Phase 4 — the storefront.** Edit the `WATCH_HOST` + `AD_EMAIL` lines at the
   top of `site/index.html`. Cloudflare serves it via **Workers Static Assets**,
   wired to this repo through Cloudflare's Git integration (`wrangler.jsonc`
   points `assets` at `site/`) — every push to `main` auto-deploys. Live at
   `ch0.ripostelabs.xyz`.
6. **Phase 5 — go live sometimes.** OBS to the same RTMP key for Ground Zero
   remotes and Lab Hour.
7. **Phase 6 — more machines (optional).** `tools/bootstrap-node.sh` stands up a
   node from a bare box in one command, and a second playout node on the same
   shared media becomes a standby that takes over if the first dies. Note what
   this does and doesn't buy you — a linear channel can't be load-balanced, only
   made redundant. See [clustering](docs/clustering.md).

## Configuration, all of it

- **`.env`** (from [`.env.example`](.env.example)) — domains, stream key,
  channel URL, media root, and (optional) the Owncast token for the now-playing
  bridge. Used by the compose stack, the uplink, and the tools.
- **`site/index.html` `CONFIG` block** — stream URL, Owncast base (for the
  ON AIR light, receiver count, and the live NOW SHOWING title), ad-submission
  email, chat and lab links. Also the **`P2P_*` keys** (WebRTC segment sharing,
  on by default — viewers offload the tower for each other) and `PEERTUBE_EMBED`
  (set it to run the PeerTube tower's player instead; see [`vps/peertube/`](vps/peertube/)).
- **Everything else** lives in the ErsatzTV and Owncast admin UIs, documented
  in the build guide.

Two secrets, both in `.env` (gitignored) and nowhere else: the **stream key**
(the world vs. your airwaves) and, if you run the marquee, an **Owncast access
token**. Cloudflare needs no secret in the repo — its Git integration deploys
the storefront on every push on its own.

## The sponsor

Channel Z0 is sponsored by **Riposte Laboratories**
([ripostelabs.xyz](https://ripostelabs.xyz)) — an engineering company that
transforms discarded plastic and end-of-life battery cells into durable,
modular products. Between programs, you'll see what the lab has been building
lately. The storefront speaks the lab's design language: paper, ink, one red,
spec sheets, and esh's checkers.

*PARRY · RIPOSTE · RECYCLE · REPEAT ♻*

## License

Code and configuration are [MIT](LICENSE). The *Channel Z0* and *Ground Zero*
names, show concepts, and the Riposte Laboratories marks and brand language
are not granted by the licence — build your own station with this plumbing,
but make it yours. (The Prelinger Archive material the guide points at is
public domain; anything you air still has to be yours to air. See
[`docs/ad-standards.md`](docs/ad-standards.md).)

---

*This station concludes its broadcast day at midnight. Colour bars until sunrise.*

---

## Brand

This project follows the [Riposte Laboratories design system](https://github.com/armeehn/riposte-brand) — published at
[ripostelabs.xyz/brand](https://ripostelabs.xyz/brand/). See [`BRAND.md`](BRAND.md) for what
conforms, what deliberately diverges, and why.

<table>
<tr>
<td><b>DOC NO. RL-Z0-A</b><br>REV. A &middot; EST. 2026</td>
<td align="right"><b>PARRY &#9851; RIPOSTE &#9851; RECYCLE &#9851; REPEAT</b><br>Riposte Laboratories Inc.</td>
</tr>
</table>
