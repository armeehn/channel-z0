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
| [`docs/pdf/docs-build-guide.pdf`](docs/pdf/docs-build-guide.pdf) | **Start here.** The full station build, Phase 0 → on-air |
| [`docs/pdf/docs-programming.pdf`](docs/pdf/docs-programming.pdf) | **The broadcast week.** The full schedule, the show bible, and the ErsatzTV mapping |
| [`docs/pdf/docs-archive-fetch.pdf`](docs/pdf/docs-archive-fetch.pdf) | **Stocking the library.** Public-domain intake from the Internet Archive |
| [`docs/pdf/docs-clustering.pdf`](docs/pdf/docs-clustering.pdf) | **More than one machine.** Node roles, failover, and what can't be load-balanced |
| [`docs/pdf/docs-self-hosting.pdf`](docs/pdf/docs-self-hosting.pdf) | Run master control on a homelab — Proxmox & TrueNAS, GPU passthrough, tips |
| [`docs/pdf/docs-gear-and-costs.pdf`](docs/pdf/docs-gear-and-costs.pdf) | Hardware picks, VPS comparison, bandwidth math, budgets |
| [`docs/pdf/docs-weather.pdf`](docs/pdf/docs-weather.pdf) | **On-air graphics.** The bug, the weather desk, the crawl, and the traps in ErsatzTV’s graphics engine |
| [`docs/pdf/docs-ad-standards.pdf`](docs/pdf/docs-ad-standards.pdf) | The one-page rulebook for locally submitted commercials |
| [`docs/pdf/docs-ideas.pdf`](docs/pdf/docs-ideas.pdf) | The writers' room — what's shipped, what's next |
| [`docs/comment-relay.md`](docs/comment-relay.md) | **The comment relay.** How a viewer's comment gets from the storefront into the chat room: shape, allowance, house rules, post |
| [`site/index.html`](site/index.html) | The storefront — tabbed sections pinned to the window, live player (pause, volume, full screen), the tower's live chat in the rail, program grid, ad submissions (Riposte Labs design language) |
| [`site/retro/index.html`](site/retro/index.html) | The original CRT-and-wood-cabinet version, preserved |
| [`site/tv/index.html`](site/tv/index.html) · [`site/ch0.m3u`](site/ch0.m3u) | The channel as a television (`/tv`, for a smart TV browser) and as a one-line playlist for IPTV apps and Live TV tuners |
| [`site/_headers`](site/_headers) · [`site/_redirects`](site/_redirects) | Cloudflare headers + short links (`/watch`, `/lab`) |
| [`vps/`](vps/) | The tower: Owncast `docker-compose.yml` + `Caddyfile` (and [`vps/peertube/`](vps/peertube/) — a peer-to-peer alternative tower) |
| [`playout/`](playout/) | Master control: `compose.yml` (containerized), ErsatzTV launcher, uplink supervisor, now-playing bridge |
| [`tools/`](tools/) | Station scripts — see below |
| [`worker/`](worker/) | The storefront Worker — the moderated comment relay and nothing else ([manual](docs/comment-relay.md)) |
| [`wrangler.jsonc`](wrangler.jsonc) | Cloudflare Worker config (serves `site/` as static assets at `ch0.ripostelabs.xyz`, plus the relay) |
| [`.env.example`](.env.example) | Domains, stream key, media root, tokens — copy, fill, never commit |

### Station scripts

| Script | Job |
|---|---|
| `tools/bootstrap-node.sh` | Stand up a node from a bare machine — playout, tower, or worker ([manual](docs/pdf/docs-clustering.pdf)) |
| `tools/make-media-tree.sh` | Create the media library layout on the playout PC |
| `tools/z0-weather.sh` | The weather desk — renders the corner card, the crawl and the forecast segment ([manual](docs/pdf/docs-weather.pdf)) |
| `tools/wire-graphics.py` | Wires the graphics elements and forecast slots into the broadcast week ([manual](docs/pdf/docs-weather.pdf)) |
| `tools/fetch-archive.sh` | Stock the library from archive.org — public domain only, resumable ([manual](docs/pdf/docs-archive-fetch.pdf)) |
| `tools/make-proxies.sh` | Build a test library — tiny stand-ins with identical runtimes, for trying schedules |
| `tools/test-failover.sh` | Prove the cluster fails over and never double-publishes |
| `tools/test-generators.sh` | Prove the card generators still make cards — arguments, text, 1080p/30 conformance |
| `tools/test-broadcast.sh` | Fire a live test pattern at the tower (build guide, Phase 1.5) |
| `tools/test-player-controls.mjs` | Drive the storefront player in a real browser — pause/resume-at-live, mute + volume, full screen (needs the channel on air) |
| `tools/test-section-tabs.mjs` | Drive the storefront's section tabs in a real browser — one panel at a time, deep links, keyboard, and that nothing spills past the fold |
| `tools/test-rights-flag.mjs` | Drive SEC.05 in a real browser — the provenance copy, and that the flag link carries the programme and a stamped moment into the mailto, tower up or down |
| `tools/test-chat-panel.mjs` | Drive the rail's live chat in a real browser — the SPEC/CHAT switch, the wire to the tower, and the sanitiser against hostile message bodies |
| `tools/test-chat-composer.mjs` | Drive the comment box in a real browser against a stubbed relay — every way it can say yes, no, and wait |
| `tools/test-comment-relay.mjs` | Drive the relay Worker with no browser and no network — shape, rate limits, fail-closed moderation, the tower call |
| `tools/check-ad.sh` | Screen a submitted spot: length, codecs, true loudness (read-only) |
| `tools/normalize-ad.sh` | Clear a submitted spot for air: 1080p/30, loudness-normalized |
| `tools/z0-video-tail.sh` | Find clips whose picture ends before their sound (they log as 0.6–0.9x and drift the tower) and loop them to length |
| `tools/make-colorbars.sh` | Generate the midnight sign-off bars (with optional silence) |
| `tools/make-testcard.sh` | Generate the station test card — the branded signal-check pattern with a 1 kHz line-up tone |
| `tools/make-signoff.sh` | Generate the nightly sign-off — the "broadcast day concludes" card dissolving into colour bars |
| `tools/make-ident.sh` | Generate station idents — the "NOW WATCHING CHANNEL Z0" bumpers |
| `tools/make-slate.sh` | Generate slate cards — technical difficulties, sign-off, please stand by |
| `tools/make-bug.sh` | Generate the channel bug (watermark PNG) for ErsatzTV |

The nine `tools/test-*.mjs` suites run with `npm ci && npm test` (or one at a
time with `node tools/test-<name>.mjs`). The eight browser suites need a full
Chrome, not a headless shell: they default to the puppeteer cache and take a
`CHROME=/path/to/chrome` override. `test-now-plate` and `test-player-controls`
tune into the live tower and go red when it is off air. CI runs only
`test-comment-relay`; the rest are local, see the note at the end of
`.github/workflows/verify.yml`.

## Quickstart

The short version — the [build guide](docs/pdf/docs-build-guide.pdf) has every command.

1. **Phase 0 — names.** A domain, a VPS, two DNS records. See
   [gear-and-costs](docs/pdf/docs-gear-and-costs.pdf) for picking the VPS (spoiler: it
   can be $0).
2. **Phase 1 — the tower.** On the VPS: `vps/docker-compose.yml` up, Caddy
   configured, then immediately change Owncast's default admin password and
   stream key. Prove the pipe with `tools/test-broadcast.sh`.
3. **Phase 2 — master control.** On the playout PC (or a homelab box — see
   [self-hosting](docs/pdf/docs-self-hosting.pdf)): `tools/make-media-tree.sh`, fill the
   library (`tools/fetch-archive.sh --all` stocks the public-domain half —
   see [archive-fetch](docs/pdf/docs-archive-fetch.pdf)), then either
   `playout/ersatztv.sh` or the whole containerized stack
   with `cd playout && docker compose up -d`. Build the schedule and ad-break
   filler in the ErsatzTV UI.
4. **Phase 3 — the uplink.** The `uplink` service in `playout/compose.yml`
   carries one stream to the tower and reconnects forever (or install the
   bare-metal `playout/z0-uplink.service`). Optionally add the now-playing
   bridge: `docker compose --profile nowplaying up -d`. You now run a
   television station.
5. **Phase 4 — the storefront.** `station.env` + `tools/rebrand.py` set the
   tower host and mailbox in `site/index.html`. Cloudflare serves it via **Workers Static Assets**,
   wired to this repo through Cloudflare's Git integration (`wrangler.jsonc`
   points `assets` at `site/`) — every push to `main` auto-deploys. Live at
   `ch0.ripostelabs.xyz`.
6. **Phase 5 — go live sometimes.** OBS to the same RTMP key for Ground Zero
   remotes and Lab Hour.
7. **Phase 6 — more machines (optional).** `tools/bootstrap-node.sh` stands up a
   node from a bare box in one command, and a second playout node on the same
   shared media becomes a standby that takes over if the first dies. Note what
   this does and doesn't buy you — a linear channel can't be load-balanced, only
   made redundant. See [clustering](docs/pdf/docs-clustering.pdf).

## Configuration, all of it

- **`.env`** (from [`.env.example`](.env.example)) — domains, stream key,
  channel URL, media root, and (optional) the Owncast token for the now-playing
  bridge. Used by the compose stack, the uplink, and the tools.
- **`site/index.html` `CONFIG` block** — stream URL, Owncast base (for the
  ON AIR light, receiver count, and the live NOW SHOWING title), ad-submission
  email, chat and lab links. Also the **`P2P_*` keys** (WebRTC segment sharing,
  on by default — viewers offload the tower for each other), the **`CHAT_*`
  keys** (see below) and `PEERTUBE_EMBED` (set it to run the PeerTube tower's
  player instead; see [`vps/peertube/`](vps/peertube/)).

### The live chat in the rail

SEC.01's right-hand rail carries two things behind one switch in the card's
head bar: the **SPEC** card and the tower's **CHAT**. It opens on CHAT, and the
viewer's choice is remembered. They share the column rather than stacking
because there is only ~16px of slack under the SPEC card on a 1280×900 window —
measured, not guessed.

The chat is **read-only, on purpose.** The storefront reads the room straight
from Owncast (`/api/chat` for the backlog, then a websocket) and posts nothing.
A page that could post would have to carry a chat token, and a token in a public
page belongs to everyone who views it. The way in for viewers is the tower
itself, linked at the foot of the panel.

**The way in is the relay** — `worker/`, documented in
[`docs/comment-relay.md`](docs/comment-relay.md). A viewer's comment goes to a
Worker route on this origin, which checks its shape, spends the viewer's
allowance, puts it in front of a small model against the house rules, and only
then speaks to Owncast with a server-side token. Failure is closed: if the
moderator cannot be reached, nothing is posted.

Until `OWNCAST_TOKEN` and a moderator are configured the relay reports itself
closed, the comment box never appears, and the panel keeps its link to the
tower. **A storefront deployed without those secrets looks exactly as it did
before the relay existed.**

Three things about the tower are worth knowing before touching any of it, all
of them found the hard way and all of them commented at the chat block in
`site/index.html`:

- the register POST must be a **simple request** — send `Content-Type:
  application/json` and the preflight is refused by the tower's
  `Access-Control-Allow-Headers`, and the whole panel dies with "Failed to
  fetch";
- **`USER_JOINED` is broadcast on a token's first connection only**, so
  persisting the token in `localStorage` is what stops every page view
  announcing a new arrival in the room;
- message bodies are **HTML the tower rendered from someone else's markdown**,
  and this page sets no CSP, so they go through an allowlist and nothing else.
- **Everything else** lives in the ErsatzTV and Owncast admin UIs, documented
  in the build guide.

The relay's own two secrets live in Cloudflare, set with `wrangler secret put`
and never in the repo: **`OWNCAST_TOKEN`** (an Owncast token scoped
`CAN_SEND_MESSAGES` — its *name* is the author the chat room sees) and
**`ANTHROPIC_API_KEY`** (skip it for `MODERATION_PROVIDER=workers-ai` or `off`).

Two more secrets, both in `.env` (gitignored) and nowhere else: the **stream key**
(the world vs. your airwaves) and, if you run the marquee, an **Owncast access
token**. Cloudflare needs no secret in the repo — its Git integration deploys
the storefront on every push on its own.

## The sponsor

Every station has someone paying for the tower. Here it is
**Riposte Laboratories** ([ripostelabs.xyz](https://ripostelabs.xyz)), whose
Lab Hour shows what the lab has been building lately and whose design
language the storefront borrows: paper, ink, one red, spec sheets, checkers.
The name comes from `station.env`; the look is the `:root` block at the top
of `site/index.html`.

*PARRY · RIPOSTE · RECYCLE · REPEAT ♻*

## Make it yours

This repository is meant to be forked. Every name, domain, mailbox, show
title and place it carries lives in [`station.env`](station.env); edit that
file and run `python3 tools/rebrand.py` to have the whole tree, schedules
and file names included, follow it. [`FORKING.md`](FORKING.md) is the
checklist from fork to first sign-on.

## License

<!-- rebrand:off -->
Code and configuration are [MIT](LICENSE). The *Channel Z0* and *Ground Zero*
names, show concepts, and the Riposte Laboratories marks and brand language
are not granted by the licence — build your own station with this plumbing,
but make it yours (`station.env` is where that starts).
<!-- rebrand:on --> (The Prelinger Archive material the guide points at is
public domain; anything you air still has to be yours to air. See
[`docs/pdf/docs-ad-standards.pdf`](docs/pdf/docs-ad-standards.pdf).)

---

*This station concludes its broadcast day at midnight. Colour bars until sunrise.*

---

## Brand

<!-- rebrand:off -->
The upstream station follows the [Riposte Laboratories design system](https://github.com/armeehn/riposte-brand)
([ripostelabs.xyz/brand](https://ripostelabs.xyz/brand/)); [`docs/pdf/brand.pdf`](docs/pdf/brand.pdf) records what
conforms, what deliberately diverges, and why. A fork owes it nothing.
<!-- rebrand:on -->

<table>
<tr>
<td><b>DOC NO. RL-Z0-A</b><br>REV. A &middot; EST. 2026</td>
<td align="right"><b>PARRY · RIPOSTE · RECYCLE · REPEAT</b><br>Riposte Laboratories Inc.</td>
</tr>
</table>
