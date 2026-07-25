# CHANNEL Z0 — Ideas & Roadmap (Station Bulletin № 2)

*A local channel is a premise, not a product; it can keep growing without ever
getting bigger. This is the writers' room — what's already on the air, and what's
sketched on the whiteboard. Steal freely; the plumbing is MIT.*

---

## Shipped in this pass

These went from idea to implementation and are in the repo now.

- **The live marquee.** The storefront's "NOW SHOWING" used to read from a
  hand-typed schedule. Now [`playout/nowplaying.py`](../playout/nowplaying.py)
  reads what ErsatzTV is *actually* airing from its XMLTV guide and writes it
  into Owncast's stream title; the site shows the real program, live. Ships as
  an optional service in [`playout/compose.yml`](../playout/compose.yml)
  (`--profile nowplaying`). This is the difference between a webpage about a
  channel and a webpage *tuned to* one.

- **The whole home side in one file.** [`playout/compose.yml`](../playout/compose.yml)
  containerizes master control — ErsatzTV, the uplink relay (an `ffmpeg -c copy`
  loop that replaces the systemd unit), and the marquee — so it drops onto a
  Proxmox LXC or TrueNAS box without ceremony. See
  [`docs/self-hosting.md`](self-hosting.md).

- **Station identity, generated.** The build guide asked for bumpers, a channel
  bug, and a technical-difficulties slate, then never made them. Now:
  - [`tools/make-ident.sh`](../tools/make-ident.sh) — the "NOW WATCHING
    CHANNEL Z0" bumpers the Station ID filler rotates.
  - [`tools/make-slate.sh`](../tools/make-slate.sh) — full-screen slate cards
    (technical difficulties, sign-off, please-stand-by), 1080p, on-brand.
  - [`tools/make-bug.sh`](../tools/make-bug.sh) — the transparent channel bug
    PNG for ErsatzTV's watermark.

  All three speak the storefront's language — monospace on ink, one red, the
  RL-Z0 designation — so the on-screen channel and the website look like one
  station.

- **Pre-flight for spots.** [`tools/check-ad.sh`](../tools/check-ad.sh) reads a
  submission and tells you its length, codecs, and true loudness before you
  accept it — the screening step that pairs with `normalize-ad.sh`.

- **The broadcast week, written down.** The build guide gave master control a
  one-paragraph "starting rhythm" and an empty ErsatzTV; now
  [`docs/programming.md`](programming.md) is the whole week — five dayparts, a
  protected 19:00 flagship, themed nights (Atomic Tuesday, Friday Night Feature,
  the Saturday double bill), the show bible for what's ours, and the exact
  ErsatzTV mapping (collections, fixed-start anchors, the weekend schedule). The
  storefront's program grid ([`site/index.html`](../site/index.html)) is now its
  machine-readable twin: a real seven-day `WEEK` with day tabs, so viewers can
  flip through the week, not just today. Guide and guide-on-the-wall, in sync.

- **On Cloudflare.** The storefront ships to Cloudflare (Workers Static Assets)
  (`ch0.ripostelabs.xyz` today, `channelz0.tv` when purchased) with tidy short
  links (`/watch`, `/lab`) and security headers. The tower stays on the VPS.

---

## On the workbench

Sketches worth building next, roughly in order of bang-for-effort.

### Programming
- **The Neighbourhood Desk, for real.** A `bulletin.json` the storefront renders
  as a scrolling ticker — lost cats, garage sales, the school play. Locals are
  the content; the ticker is the cheapest possible community TV.
- **Ask the alien.** A submission form (a Cloudflare Worker → email or R2)
  where locals leave questions for the Ground Zero correspondent to ask the
  neighbourhood via baguette. Turns viewers into a writers' room.
- **The sign-off anthem.** A 60–90s nightly close — a slow pan over the lab, the
  RL-Z0 card, a bit of music you own — generated once and aired at 00:00 before
  the colour bars. `make-slate.sh` is the seed; this is its cinematic cousin.
- **Emergency Broadcast crawl.** A parody EAS: the checker band, the two-tone,
  a crawl of gloriously low-stakes alerts ("A CASSEROLE HAS BEEN LEFT
  UNATTENDED"). Aired rarely, on purpose.

### On-air polish
- **Lower-thirds kit.** An ffmpeg/overlay template for Ground Zero — name,
  location, "DEFINITELY HUMAN" — so field interviews get a broadcast chyron.
- **The QR corner.** A tiny static QR to the storefront, burned into the bug
  area during idents, so anyone who wanders past a TV can find the stream.

### The site
- **Full week guide.** ErsatzTV already serves XMLTV; a small build step could
  turn a week of it into a printable TV-guide page (very on-brand as a zine).
- **Receiver map / "who's tuned in."** Owncast reports viewer counts; a sparkline
  of the day's audience makes the "someone's always watching" promise visible.

### The bigger swing
- **Channel Z1.** The architecture is per-channel, not per-station. A second
  ErsatzTV channel + a second Owncast is a sibling network (Z1: overnight
  ambient? all-cartoons?). The storefront becomes a dial.

---

*Ideas are cheap; airtime is free while we're small. Build the ones that make
the neighbourhood lean in.*
