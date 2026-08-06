# CHANNEL Z0 — Programming Guide (Station Bulletin № 3)

```
┌───────────────────────────────────────────────────────────┐
│   CHANNEL Z0 · CH 0 · DESIG RL-Z0                         │
│   THE BROADCAST WEEK — sign-on 06:00, sign-off 00:00      │
│   colour bars until sunrise, exactly as intended          │
└───────────────────────────────────────────────────────────┘
```

The [build guide](build-guide.md) gives master control a *starting rhythm* — one
paragraph of dayparts — and then hands you an empty ErsatzTV. This is the rest of
the sentence: the actual **programming**. A full broadcast week, every block
defined, the show bible for what's ours, and the exact ErsatzTV mapping so the
schedule on paper becomes the schedule on air.

It is deliberately buildable from public-domain material and local submissions
alone. Nothing here needs a rights cheque. See [`docs/ad-standards.md`](ad-standards.md)
for the one rule that keeps it that way: *air only what's yours to air.*

> **The storefront reads this.** The program grid at
> [`site/index.html`](../site/index.html) is the machine-readable twin of the
> table below; the two are meant to say the same thing. Edit the schedule there
> and here together, or the guide and the guide-on-the-wall drift apart.

---

## The shape of a broadcast day

Old television had a *shape* — you could tell the time by what was on. Z0 keeps
it. Five dayparts, a protected flagship, a hard midnight sign-off, and colour
bars overnight so the signal never goes to black.

| Daypart | Hours | Mood | Fed mostly by |
|---|---|---|---|
| **Sign-on & morning** | 06:00 – 11:00 | Gentle; the day clears its throat | Slow TV, cartoons, Prelinger shorts |
| **Midday** | 11:00 – 14:00 | Working hours, on in the background | Lab Hour, music loops, the bulletin |
| **Afternoon** | 14:00 – 18:00 | Matinee and the after-school return | A feature, then cartoons again |
| **Prime** | 18:00 – 22:00 | Lean in; the neighbourhood is home | The Desk, **Ground Zero**, the night's feature |
| **Late & sign-off** | 22:00 – 00:00 | Wind down; last ones awake | Encore, a mellow block, the sign-off ritual |
| *(overnight)* | 00:00 – 06:00 | Dark | **Colour bars** (`Dead Air` filler) |

The two fixed points that never move: **19:00 GROUND ZERO** (the flagship —
protect the slot) and **00:00 SIGN-OFF** (the ritual close). Everything else can
flex; those two are the station's heartbeat.

---

## The weekly grid

The weekday spine is the same Monday through Friday; the **20:00 feature** and the
**23:00 late block** are themed by night, which is what gives the week a memory
("it's Tuesday, so it's a monster movie"). Weekends restructure the mornings for
people who are home, and add a second feature.

### Weekdays (Mon – Fri)

| Time | Programme | What it is |
|---|---|---|
| 06:00 | **SIGN-ON · MORNING PATTERN** | Anthem, test card, the day begins |
| 06:30 | **STRETCH & COFFEE** | Slow television from around the neighbourhood |
| 07:00 | **CARTOON BLOCK** | Public-domain toons, drawn before your grandparents met |
| 09:00 | **PRELINGER THEATRE** | Vintage PSAs & educational shorts; trust the narrator |
| 11:00 | **LAB HOUR** | What Riposte Labs is building this week, sometimes live |
| 12:00 | **LUNCH LOOPS** | Music + the community bulletin board |
| 14:00 | **AFTERNOON PICTURE SHOW** | A matinee feature older than streaming |
| 16:00 | **CARTOON BLOCK II** | The toons return, as toons do |
| 18:00 | **NEIGHBOURHOOD DESK** | Notices, events, found cats, lost causes |
| **19:00** | **▸ GROUND ZERO** | Alien street interviews via baguette — the flagship |
| 20:00 | **PRIME FEATURE** *(themed, below)* | The big picture, local ad breaks as nature intended |
| 22:00 | **GROUND ZERO — ENCORE** | Tonight's contact, retransmitted for the late crowd |
| 23:00 | **LATE BLOCK** *(themed, below)* | Mellow signals for the last ones awake |
| **00:00** | **SIGN-OFF** | The ritual close, then colour bars until sunrise |

### The themed nights

The spine above stays put; only the **20:00** and **23:00** identities change. This
is the cheapest possible way to make seven identical loops feel like seven
different evenings.

| Night | 20:00 PRIME FEATURE | 23:00 LATE BLOCK | Pull from |
|---|---|---|---|
| **MON** | **MONDAY NIGHT NOIR** — crime, shadows, a hat | **AFTER HOURS** — jazz loop + bulletin | PD noir & crime features |
| **TUE** | **ATOMIC TUESDAY** — sci-fi, monsters, rockets | **THE LATE TRANSMISSION** — vintage sci-fi shorts | PD sci-fi / creature features |
| **WED** | **WORKBENCH THEATRE** — how-things-are-made, docs | **NIGHT PATTERN** — ambient | Prelinger industrials, PD docs |
| **THU** | **SERIAL NIGHT** — a chapter, a cliffhanger | **CHAPTER'S END** — the recap loop | PD adventure serials |
| **FRI** | **FRIDAY NIGHT FEATURE** — the prestige pick | **THE LATE LATE SHOW** — cult & camp | Your best PD feature; the weird one |
| **SAT** | **SATURDAY DOUBLE BILL** — feature one | *(→ into feature two, ~00:30 sign-off)* | Two crowd-pleasers |
| **SUN** | **SUNDAY CINEMA** — a classic, unhurried | **NIGHT PATTERN** — early wind-down | PD classics / drama |

### Weekends (Sat & Sun)

Mornings shift for a house that's awake early and off the clock. Cartoons come
forward and run long (the **Cartoon Carnival**); the afternoon opens up.

**Saturday** — the big night.

| Time | Programme |
|---|---|
| 06:00 | SIGN-ON · MORNING PATTERN |
| 07:00 | **CARTOON CARNIVAL** — the long block, three hours of toons |
| 10:00 | PRELINGER THEATRE |
| 11:00 | LAB HOUR |
| 12:00 | LUNCH LOOPS |
| 13:00 | **MATINEE DOUBLE** — an afternoon feature |
| 16:00 | CARTOON BLOCK II |
| 18:00 | NEIGHBOURHOOD DESK — the weekend edition |
| **19:00** | **▸ GROUND ZERO** |
| 20:00 | **SATURDAY DOUBLE BILL** — feature one |
| 22:30 | **SATURDAY DOUBLE BILL** — feature two |
| ~00:30 | SIGN-OFF *(Saturday runs late; the one night it does)* |

**Sunday** — the quiet one. A slower morning, an earlier settle.

| Time | Programme |
|---|---|
| 06:00 | SIGN-ON · MORNING PATTERN |
| 06:30 | **SUNDAY SERVICE** — slow TV, long takes, the neighbourhood at rest |
| 09:00 | CARTOON CARNIVAL |
| 11:00 | PRELINGER THEATRE |
| 12:00 | LUNCH LOOPS |
| 14:00 | AFTERNOON PICTURE SHOW |
| 16:00 | CARTOON BLOCK II |
| 18:00 | NEIGHBOURHOOD DESK |
| **19:00** | **▸ GROUND ZERO** — the week-in-review contact |
| 20:00 | **SUNDAY CINEMA** — the unhurried classic |
| 22:30 | NIGHT PATTERN — the early wind-down |
| **00:00** | SIGN-OFF |

---

## The programme bible

Every recurring block, defined once. Duration is a target; the **`Pad to :00/:30`**
filler (build guide, Phase 2.3) stretches the ad break to make each slot land on
the clock, exactly like 1994. "Source" is what fills it; "Collection" is the
ErsatzTV collection the schedule item points at.

### The originals — ours, and only ours

- **GROUND ZERO** *(nightly 19:00, 30 min, flagship)*
  Alien street interviews conducted via baguette. Our correspondent picked up
  Earth's distress signal, opened a wormhole, and came to check on us — wearing a
  very convincing human skin, armed with a bread microphone. They study us; they
  do not fully understand us; they are trying. Filed nightly.
  *The dossier lives on the storefront ([`site/index.html`](../site/index.html),
  SEC.03).* Protect this slot above all others; the whole channel points at it.
  **Collection:** `Ground Zero` (show library). **Encore** at 22:00.

- **LAB HOUR** *(daily 11:00, 60 min)*
  What Riposte Laboratories is building this week — recycled-plastic and
  end-of-life-cell products, in progress. Sometimes a pre-recorded workshop tour,
  sometimes live from the bench (see build guide, Phase 5). The sponsor *is* the
  programming here, and that's allowed; it's the lab's channel.
  **Collection:** `Lab Hour` (show library) + `Lab Promos` filler.

- **NEIGHBOURHOOD DESK** *(nightly 18:00, 60 min)*
  The cheapest community television ever made: local notices, events, found cats,
  lost causes, the school play, the casserole left unattended. Runs as a card
  loop or a slow scroll over music. The content is the neighbourhood; the Desk
  just points a camera at it. *(Roadmap: a `bulletin.json` the storefront renders
  as a ticker — see [`docs/ideas.md`](ideas.md).)*
  **Collection:** `Neighbourhood Desk` (interstitials / card loop).

- **SIGN-ON / SIGN-OFF** *(06:00 / 00:00, ~2 min each)*
  The rituals that bracket the day. Sign-on: the anthem and the test card as the
  station wakes. Sign-off: the RL-Z0 card, a slow pan over the lab, goodnight —
  then colour bars until 06:00. Generate the cards with
  [`tools/make-slate.sh`](../tools/make-slate.sh); the overnight bars with
  [`tools/make-colorbars.sh`](../tools/make-colorbars.sh).
  **Collection:** `Sign-Off Ritual` → `Colour Bars` (as `Dead Air` filler).

### The acquired — public domain, curated

> 📦 *In this repo:* [`tools/fetch-archive.sh`](../tools/fetch-archive.sh) fetches
> every block below straight into the folders ErsatzTV watches — one slot per
> collection named here, public-domain-marked items only. See
> [`docs/archive-fetch.md`](archive-fetch.md) for the recipes and the manifest.

- **CARTOON BLOCK / BLOCK II / CARNIVAL** *(mornings, afternoons, weekend long-form)*
  Public-domain animation — the pre-1964 well is deep (early theatrical shorts,
  the ones whose copyrights lapsed). The Carnival is just the Block, scheduled
  long, for weekend mornings. **Collection:** `Cartoons`.

- **PRELINGER THEATRE** *(mornings, 60–120 min)*
  The Internet Archive's [Prelinger collection](https://archive.org/details/prelinger):
  educational films, PSAs, industrial shorts, mid-century strangeness. Exactly the
  texture an old channel needs, and legally spotless. **Collection:** `Prelinger`.

- **THE FEATURES** *(matinee 14:00, prime 20:00, themed by night)*
  Public-domain features, sorted into the themed nights above. The move is to keep
  a few themed sub-collections so the schedule can ask for "a noir" or "a monster
  movie" by name. **Collections:** `Features · Noir`, `Features · SciFi`,
  `Features · Docs`, `Features · Serials`, `Features · Classics`, `Features · Cult`.

- **STRETCH & COFFEE / SUNDAY SERVICE / NIGHT PATTERN** *(the slow blocks)*
  Long-take "slow television" — a fixed camera on something calm, or a music loop
  over a still. Ambient by design; on in the background of a kitchen. Owns-your-
  rights music only (or silence with a nice picture). **Collection:** `Slow TV`.

- **LUNCH LOOPS / AFTER HOURS** *(midday & late music)*
  Music you own, looped, over the bulletin or a still card. The daytime version
  carries the Neighbourhood Desk crawl; the late version is just the jazz.
  **Collection:** `Music Loops`.

### The connective tissue — filler, always running

These aren't scheduled; they're **filler presets** that the pad-to-the-half-hour
machine deals between and around everything above. This is the layer that turns a
playlist into a *station*.

| Filler preset | Draws from | When |
|---|---|---|
| `Ad Break` | `Local Ads` + `Lab Promos` + `Vintage PSAs` | Mid-roll, padded to :00/:30 |
| `Station ID` | `Bumpers` (from [`make-ident.sh`](../tools/make-ident.sh)) | Pre/post-roll around each show |
| `Dead Air` | `Colour Bars` | Fallback if a slot ever runs dry, and overnight |

The **channel bug** (the RL-Z0 watermark from [`make-bug.sh`](../tools/make-bug.sh))
rides over all of it, always on, never explained. Old-TV physics.

---

## Building it in ErsatzTV

The grid above maps onto ErsatzTV's model cleanly. In order:

1. **Libraries & collections.** Beyond the build guide's basics, add the themed
   feature sub-collections (`Features · Noir`, `· SciFi`, `· Docs`, `· Serials`,
   `· Classics`, `· Cult`), plus `Cartoons`, `Prelinger`, `Slow TV`, `Music Loops`,
   `Neighbourhood Desk`. Tag-based collections work well: tag a film `noir` and it
   flows into Monday night on its own.

2. **One schedule per day-type, or one big rotation.** Simplest is a single
   **weekly** schedule where each item declares its day. ErsatzTV's schedule items
   run in order and loop; use the **fixed start time** option on the anchors
   (06:00 sign-on, 11:00 Lab Hour, **19:00 Ground Zero**, 20:00 feature, 00:00
   sign-off) so the tentpoles never drift, and let the flexible blocks fill between
   them. Pad every item to :00/:30.

3. **Protect 19:00.** Give Ground Zero a fixed start and enough runtime that no
   overrun upstream can push it. If a feature runs long, the *feature* gets cut by
   the next fixed anchor — never the flagship.

4. **Themed nights = collection swaps.** The 20:00 and 23:00 items point at a
   different themed collection per weekday. In ErsatzTV that's seven schedule
   items (one per night) or a smart collection filtered by weekday — either way,
   Tuesday pulls `Features · SciFi` and Friday pulls `Features · Cult`.

5. **Weekends = a second schedule.** Sat/Sun differ enough (earlier cartoons, the
   double bill, the late Saturday) to warrant their own schedule, activated by
   day-of-week. Keep the anchors (sign-on, Ground Zero, sign-off) identical so the
   station still feels like itself on a Saturday.

6. **Overnight is not scheduled.** Don't program 00:00–06:00. Let the `Dead Air`
   filler (`Colour Bars`) hold the signal until the 06:00 sign-on item fires. The
   station is *closed*; that's the point.

Sanity-check the whole thing in VLC against `http://playout-pc:8409/iptv/channel/1.ts`,
and confirm ErsatzTV's guide at `/iptv/xmltv.xml` shows the tentpoles at the right
times — that guide is what [`playout/nowplaying.py`](../playout/nowplaying.py)
reads to tell the storefront what's on.

---

## Keeping the guide and the air in sync

Three places describe the schedule; keep them saying the same thing:

1. **This file** — the human-readable programme bible (edit first).
2. **[`site/index.html`](../site/index.html)** — the `WEEK` schedule object the
   storefront renders as the program grid. It's the same grid, as data.
3. **ErsatzTV** — the actual playout, built per the mapping above. Its XMLTV guide
   is the *truth* on air; the live "NOW SHOWING" line on the site comes from there,
   not from the grid, so a schedule item can slip and the marquee still tells no
   lies.

When the air and the grid disagree, the air wins and the grid is the promise. Keep
the promise small enough to keep.

---

*Programming is just a shape you put on time. Ours has a flagship at seven and
the lights off at midnight. Build the rest to make the neighbourhood lean in.*
