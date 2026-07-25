# CHANNEL Z0 — Gear & Cost Plan

*Prices checked July 2026; treat every number as "about." The architecture is designed so the expensive thing (serving viewers) is rented tiny, and the cheap thing (one uplink stream) is all your house ever pays for.*

---

## The two machines

Channel Z0 runs on exactly two computers: the **playout PC** at home (runs the schedule, encodes the stream once, 24/7) and the **VPS** in a datacenter (copies that stream to every viewer). Everything else — cameras, baguettes — is production, not infrastructure.

---

## 1 · The playout PC

The only real requirement is a **hardware H.264 encoder**, so encoding costs ~5% CPU instead of 100%. Any Intel chip from roughly the last decade has one (Quick Sync); any NVIDIA card has NVENC.

| Option | Cost | Power draw | Verdict |
|---|---|---|---|
| A PC you already own | $0 | 30–60 W | Start tonight. Promote it to full-time if it behaves. |
| Used Dell OptiPlex / Lenovo Tiny (i5 6th-gen+, SFF) | $60–120 | 20–35 W | eBay/refurb classics. Quick Sync, quiet, sturdy. |
| **N100/N150 mini PC (Beelink, GMKtec, etc.)** | **$130–180** | **~10 W** | **The pick.** Silent, sips power, Quick Sync handles this job with its eyes closed. |
| Raspberry Pi 5 | ~$80 | 5 W | Skip — the Pi 5 dropped hardware H.264 *encoding*, so it's the wrong cheap computer for a TV station. |

Storage: the media library lives here. A 1 TB SSD (~$50–60 if not included) holds hundreds of hours of 1080p. **Connect via ethernet, always.**

Electricity at LA-ish rates (~$0.30/kWh, running 24/7): a 10 W mini ≈ **$2/mo**, a 35 W desktop ≈ $8/mo, a 60 W tower ≈ $13/mo. The mini PC pays for its own purchase price in saved power inside 1–2 years.

Add a small UPS (~$60) for the modem + router + playout PC, and the station rides through power flickers like a real broadcaster.

---

## 2 · The VPS (the tower)

The VPS never transcodes — it repackages your already-encoded stream — so CPU barely matters. **The spec that matters is monthly traffic.**

### The math that sizes it

One viewer watching at 4.5 Mbps uses ~2 GB/hour. Monthly totals scale with *average concurrent viewers* (not peak — 30 people during Ground Zero and 2 overnight averages out low):

| Avg concurrent viewers | Traffic per month |
|---|---|
| 1 | ~1.5 TB |
| 3 | ~4.4 TB |
| 5 | ~7.3 TB |
| 10 | ~14.6 TB |
| 20 | ~29 TB |

*(Formula: viewers × 4.5 Mbps × 2.6M seconds/month ÷ 8 bits. At 720p/3.5 Mbps, multiply everything by 0.78.)*

### Where to rent it

| Host | Cost | Traffic | Notes |
|---|---|---|---|
| **Oracle Cloud "Always Free"** | **$0** | **10 TB/mo** | 4 ARM cores, 24 GB RAM, genuinely free. Caveats: capacity can be scarce when signing up, and idle machines have been reclaimed — fine for a station that streams 24/7 (never idle), but keep backups of your Owncast config. |
| Budget yearly boxes (RackNerd-class specials) | $12–30/**yr** | 2–6 TB/mo | Astonishing value for a small audience; watch the traffic ceiling as you grow. |
| OVHcloud US VPS | ~$5–8/mo | Effectively unmetered (speed-capped port) | US datacenters, boring and dependable. |
| Hetzner CX-line (EU) | ~€5.50/mo | 20 TB/mo | The classic pick; note Hetzner raised prices in June 2026. EU location is *fine* — HLS doesn't care about an extra 140 ms, only video calls do. |
| DigitalOcean / Vultr basic | $6–7/mo | 1–2 TB/mo | Lovely dashboards, stingy traffic for a TV station. Pass. |

**Recommendation:** start on Oracle's free tier (cost: $0, and 10 TB ≈ 6–7 average concurrent viewers). If Z0 outgrows it, that's a wonderful problem, and a 20 TB host is one evening's migration.

Domain: `.org`/`.net` ~$12–15/yr; `channelz0.tv` ~$30–40/yr because the `.tv` registry knows exactly what it's selling. Until that's bought, the storefront rides for free on a subdomain — `ch0.ripostelabs.xyz` — so the station can be on-air before the domain paperwork clears.

**Hosting the page: $0.** The storefront is fully static and lives on **Cloudflare** (a Worker serving static assets; free tier, generous bandwidth), which means the VPS carries *only* the video stream — its whole traffic budget goes to viewers, not to serving HTML. When `channelz0.tv` is purchased, add it to the same Worker as a second custom domain; nothing else moves.

---

## 3 · The Ground Zero field kit

The correspondent needs to file reports. The kit is deliberately humble — the show's premise does the heavy lifting.

| Item | Cost | Notes |
|---|---|---|
| A phone you already own | $0 | Modern phone video ≥ 90s news camera. Shoot landscape. |
| Wired lavalier mic (BOYA BY-M1 class) | ~$20–25 | The entire audio department. |
| **One (1) french baguette** | ~$3/episode | The microphone. See build notes. Recurring line item; occasionally eaten by talent. |
| Phone tripod or cheap gimbal | $20–25 | For locked-off interview shots. |
| Optional: USB HDMI capture card | ~$15–20 | Feeds a real camera into OBS for Lab Hour. |

**Baguette-mic build notes (do not skip):** hollow a narrow channel from the heel end with a chopstick; thread the lav cable through so the capsule sits just beneath the crust about two inches from the tip — close enough to pick up speech when the bread is held interview-distance from a face. Wedge the foam windscreen inside the tip (it also stops crumb noise, the medium's unique problem). Gaff-tape the cable at the heel, run it down the correspondent's sleeve. The bread reads as a prop; the audio reads as broadcast. Buy the day's baguette fresh — a stale baguette sounds different, and the locals will notice.

Human skin: talent provides their own. Wardrobe budget: $0.

---

## 4 · The bill, totaled

| Tier | One-time | Monthly | What you get |
|---|---|---|---|
| **Shoestring** (PC you own + Oracle free + .org domain) | ~$25 | **~$3** (power + domain) | The full station. Zero compromises on the viewer side. |
| **Standard** (N100 mini + field kit + Oracle free) | ~$220 | ~$3 | Silent dedicated playout, Ground Zero fully equipped. |
| **Bulletproof** (Standard + paid 20 TB VPS + UPS + .tv domain) | ~$280 | ~$12 | Survives power blips, bigger audience headroom, and the flex of a `.tv`. |

For scale: a "real" low-power TV licence, tower, and transmitter runs into six figures. Channel Z0 does the culturally identical thing for less than a pizza per month, on a signal every house already has.

---

## 5 · What growth looks like

Nothing in this plan wastes money if Z0 gets popular. The upgrade path is: **turn on P2P** (below; free, cuts the traffic in the table above) → bigger-traffic VPS (~$10–20/mo, an evening's work) → add one transcoded 480p rung in Owncast for phone viewers (needs ~2 dedicated vCPUs) → someday, a real CDN in front of the HLS. Your house's side never changes: one stream, ~5 Mbps, forever.

### Free egress relief: peer-to-peer

The traffic table above assumes the tower ships every byte to every viewer. It doesn't have to. Viewers' browsers can trade HLS segments with each other over WebRTC, so the VPS serves each segment far fewer times — and a linear channel is the ideal case, because everyone's watching the same thing at the same playhead, so the swarm is dense. It only helps once a few people watch at once (one lone viewer has no one to swarm with), and it's browser-only (native TV apps don't participate), but where it applies it's pure egress relief for $0.

Two ways to get it, pick one:

- **Keep Owncast, flip it on in the storefront.** The `P2P_*` block in [`site/index.html`](../site/index.html) is on by default — it loads [p2p-media-loader](https://github.com/novage/p2p-media-loader) next to hls.js and shows a live `N PEERS · NN% OFFLOAD` readout on the SPEC card. No tower change; falls back to plain HLS on any browser that can't play along. Before you *rely* on it, run your own WebRTC tracker (the public defaults are flaky) — see the comments on `P2P_TRACKERS`.
- **Switch the tower to PeerTube.** [`vps/peertube/`](../vps/peertube/) is a drop-in Owncast alternative with P2P and its own player built in. Heavier (Postgres + Redis, ~2 GB RAM) and only worth it at real audience size; the uplink from home doesn't change.

Rough rule of thumb: with a healthy swarm P2P can offload a large share of segment traffic, which is the difference between outgrowing a 10 TB tier and staying comfortably under it. Treat it as headroom, not a guarantee — the HTTP path is always there underneath.
