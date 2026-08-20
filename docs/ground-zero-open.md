# GROUND ZERO — opening titles

**DOC NO. RL-Z0-GND-B · REV. A**

A 60-second opening title sequence for the nightly GROUND ZERO slot, built as
an 8-bit parody of the *Mega Man X* / *X2* / *X3* openings. Everything on
screen is generated: two hand-authored bitmap fonts, one sprite, a handful of
drawing primitives, and a four-voice chiptune score. No fonts, no samples, no
stock art, no network.

| | |
|---|---|
| Source | `tools/z0-gz-open/` |
| Build | `tools/z0-gz-open/build.sh [--install]` |
| Output | `GROUND ZERO - OPENING TITLES.mp4` — 60.0 s, 640x480, 30 fps, H.264 + AAC |
| Installs to | `/mnt/main-data/channelz0/opens/groundzero/` on vile |
| Tags | `media`, `opens`, `groundzero` |
| Loudness | **-22.4 LUFS** integrated, true peak **-1.1 dBFS** |

---

## The beats

The structure is lifted from the X openings and the timings from them too: a
publisher sting, a long prologue nobody asked for, a backlit hero shot, a
push-in, and a logo that arrives harder than the material warrants.

| Frames | Time | Beat |
|---|---|---|
| 0–134 | 0:00 | **Sting.** `RIPOSTE LABORATORIES INC.` types in over ticks, flashes, and drops the tri-band. A four-note chime — the Capcom logo jingle, in D minor. |
| 135–794 | 0:04.5 | **Prologue crawl.** Twenty-six lines on a dust field, with the programme's reticle holding station off the right edge. Ends on `GROUND ZERO.` |
| 795–1094 | 0:26.5 | **The rooftop.** Kelowna at night in the rain — ridge line, the lake, the bridge, a mast. A lone figure on a parapet, silhouetted on the moon, holding a stick microphone. Two lightning strikes. |
| 1095–1244 | 0:36.5 | **Push-in.** The visor, cropped by the frame, scanlines travelling. It flares white on the cut. |
| 1245–1559 | 0:41.5 | **Logo.** `GROUND` drops, `ZERO` arrives from the right, the frame judders, the reticle takes the place of the final O, and a shine sweeps the face. |
| 1560–1799 | 0:52 | **Attract.** `PRESS START`, the transmission times, the copyright, the tri-band. |

The joke is the register, not the gags: the prologue is played completely
straight, and what it is grave about is a local news bulletin.

## Why it looks like that

**320x240, doubled.** The logical canvas is 320x240 — 4:3 with square pixels
and an 8 px tile grid — scaled to 640x480 with `neighbor`. 640x480 is what the
other station cards are authored at, and a 4:3 item pillarboxes into the
channel's 854x480 **exactly inside the on-air rails**, so no part of this is
ever drawn under the up-next strip or the weather card.

**Sixteen colours and nothing else.** Ink, bone, marigold, pink and teal come
from the station; the rest are the two ramps a night sky and a metal logo need.
Gradients are ordered dither between two of those sixteen — never a blend,
because an unlisted colour costs the whole 8-bit read. Fades are quantised to
six steps for the same reason: a palette fade steps, it does not glide.

**Two bitmap fonts, hand-authored.** `gzfont.py` holds a 6x7 uppercase face in
an 8x8 cell for all the type, and a 16x18 heavy face for the eight letters
`GROUND ZERO` needs. A hinted TTF rendered small produces soft uneven stems
that read as *small text* rather than as tiles, which is the one thing the
sequence cannot afford.

**Mega Man X is 16-bit.** The brief asked for 8-bit, so what is borrowed is the
structure, the pacing and the grammar of the shots — not the colour depth. It
is a parody of an SNES intro made by a station that could only afford an NES.

## The score

`gzaudio.py` synthesises a 2A03: two pulse channels with selectable duty, one
triangle quantised to 16 steps (no volume control, which is why the bass is
always the same loudness), and one 15-bit LFSR noise channel playing every
drum. An echo is a second, quieter note placed later on the same voice.

Pure Python and `wave` — **numpy is broken in LXC 111**, and the whole track is
a few seconds of arithmetic anyway.

D minor throughout, 150 BPM. The bed under the crawl is a bass note and an
arpeggio for eleven bars and nothing else; the lead does not arrive until the
crawl is half read, because the text is the event. Drums enter on the rooftop,
the push-in narrows to one rising line and an accelerating snare roll, and the
logo lands on a bar of silence.

Verification is by Goertzel rather than by ear: sampled windows at the sting,
the crawl bed, the rooftop lead and the held final chord each report the pitches
the score specifies.

## Rebuilding

```sh
cd tools/z0-gz-open
./build.sh                       # renders to $GZ_WORK (default /var/tmp/z0-gz-open)
./build.sh --install             # ...and scp's it to vile
```

Needs `python3` with PIL, and `ffmpeg`. Takes about fifteen seconds. Render
anywhere; run `--install` **from x** — LXC 111 has the checkout and the
toolchain but no SSH trust to vile, so the install half fails there with
`Host key verification failed`. It is
fully deterministic — no seed, no clock, no network — so the master is
regenerated rather than archived, and `*.mp4` stays gitignored like every other
piece of station media.

To look at single frames without encoding:

```sh
python3 make_frames.py /tmp/stills --stills
```

## Putting it on air

**Installing the file airs nothing.** It lands in `opens/groundzero/`, which no
pool selects, and it stays inert until the schedule names it. That is
deliberate — `cards/groundzero/` is the pool `coming_soon_gnd` *shuffles* to
pad the hour, and an opening shuffled into the middle of its own slot is worse
than no opening at all.

Three steps, in order:

1. **Install and rescan.** `./build.sh --install` (from x), then let ErsatzTV rescan
   `/media` (it does so on its own within six hours) or trigger it from the UI.
   Do **not** `UPDATE LibraryPath SET LastScan = NULL` on the live DB.
2. **Add the content key** to `playout/_content.yml`:

   ```yaml
     - search:
       key: gz_open
       query: 'type:other_video AND tag:opens AND tag:groundzero'
       order: chronological
   ```

3. **Open the slot with it** in `tools/z0-build-schedule.py`, ahead of the
   existing `pad_until` and inside the same `epg_group`:

   ```yaml
     - count: 1
       content: 'gz_open'
     - pad_until: '19:58'
       ...
   ```

   Then regenerate, deploy with `z0-day-align.py --redeploy`, and reset the
   playout. Both the 19:00 slot and the 22:00 encore take the same change.

Do steps 2 and 3 **after** the rescan has actually found the file. An empty
content pool is skipped in silence — it does not error, it leaves a hole — so
naming `gz_open` before the item exists takes the top of the hour off the air
with nothing to show for it.

---

<table>
<tr>
<td><b>DOC NO. RL-Z0-GND-B</b><br>REV. A · EST. 2026</td>
<td align="right"><b>PARRY ♻ RIPOSTE ♻ RECYCLE ♻ REPEAT</b><br>Riposte Laboratories Inc.</td>
</tr>
</table>
