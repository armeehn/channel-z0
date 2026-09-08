# GROUND ZERO — opening titles

**DOC NO. RL-Z0-GND-B · REV. F**

A 60-second cold open for the nightly GROUND ZERO slot, played straight. A
distress signal leaves Earth and is addressed to no one; it goes unanswered
for a long time; something answers; a ring of light opens and closes;
something comes down into a hillside in the Okanagan at night and nobody sees
it land. Somebody had to answer it. Then the lockup.

Everything on screen is generated: one hand-authored bitmap face for the
captions, the display face in `gzlogo.py`, a palette of ramps and gradient
tables, and a synthesised score. No fonts, no samples, no stock art, no
network. The same checkout renders the same 1800 frames and the same 60 s of
audio.

| | |
|---|---|
| Source | `tools/z0-gz-open/` |
| Build | `tools/z0-gz-open/build.sh [--install]` |
| Output | `GROUND ZERO - OPENING TITLES.mp4` — 60.0 s, 640x480, 30 fps, H.264 + AAC |
| Installs to | `/mnt/main-data/channelz0/opens/groundzero/` on vile |
| Tags | `media`, `opens`, `groundzero` |

---

## What changed in REV. F

Three instructions, taken literally:

- **More serious.** The two earlier passes were a *Mega Man X* title in
  8- and then 16-bit: a publisher sting, a fourteen-line prologue crawl, an
  orchestra hit, a judder, `PRESS START` and an attract loop. All of it is
  gone. The cue has no tempo: a drone, a pulse, strings, bells, one impact.
- **Nobody is drawn.** The correspondent was a sprite on the shore and a face
  in push-in, with a name card. She is not a character on screen any more.
  The story is told in captions, light and landscape, and the only person in
  it is implied — *somebody* had to answer. `gzart.py` (the sprite and the
  ship) is deleted.
- **16-bit, not 8.** The flat single-colour caption cells were the 8-bit
  tell. Type is now cut from a ramp — light at the top of the glyph, darker
  at the foot — with a keyline and a cast shadow. Every sky is a per-scanline
  gradient and every light source is additive colour math.

## The beats

| Frames | Time | Beat |
|---|---|---|
| 0–89 | 0:00 | **Dark.** Ink. `A CHANNEL Z0 TRANSMISSION`, small, once. The drone fades in under it. |
| 90–449 | 0:03 | **The signal.** Arcs leave the bottom-left corner, opening one way and thinning as they go. A trace of what it sounds like runs across the upper third, weakening. Top right, a readout: `1420.405 MHZ · ORIGIN EARTH · ADDRESSEE NONE`. A pulse once a second. `A DISTRESS SIGNAL / LEFT EARTH.` then `IT WAS ADDRESSED / TO NO ONE.` |
| 450–749 | 0:15 | **The field.** Stars in three depths, drifting. `IT WENT UNANSWERED / FOR A LONG TIME.` One of them brightens into a bloom as the strings come in. `THEN SOMETHING / ANSWERED.` |
| 750–989 | 0:25 | **The ring.** From the answering star a ring opens over four seconds, holds, and closes in one. Its colour goes round the circumference: light blue, white, pink, and back. It is the one thing in the sequence that says what it is about, and it says it once. A flash to bone as it shuts. |
| 990–1319 | 0:33 | **The descent.** Night over the Okanagan: three ranges by contrast, the lake carrying the sky. A small bright point comes down the diagonal into the middle range. A flash, a bloom that cools over two seconds, dust rising and thinning, the lake taking the glow. `NOBODY SAW IT LAND.` Fade. |
| 1320–1559 | 0:44 | **The claim.** `SOMEBODY HAD TO / ANSWER IT.` over a red rule, and under it `FIELD INTERVIEWS · THE OKANAGAN`. |
| 1560–1799 | 0:52 | **The lockup.** A warm light grows behind the zero and `GROUND ZERØ` resolves out of it. The horizon draws outward from under the zero, dent first. Designation, times, the copyright line, the tri-band. Fade to ink on an open fifth. |

Captions sit low, two short lines at most, nineteen cells each — the register
of a subtitle, not a crawl. `check_fits()` refuses to render one that would
not fit, and refuses any character the face does not have.

## Nothing here is a crosshair

An earlier pass built the whole identity around a reticle — the O of `ZERO`
*was* one, the crawl's mark was one, and the strapline read `EPICENTRE`. All of
it is gone, deliberately:

| Was | Is |
|---|---|
| The O of ZERO as a targeting reticle | the zero of ZERØ: a ring and ONE bar, the slashed zero — `test_logo.py` proves the midlines inside the ring are empty |
| A reticle holding station in the crawl | the transmission: concentric *arcs*, opening one way |
| `DESIG. RL-Z0-GND · EPICENTRE` | `DESIG. RL-Z0-GND · LANDING SITE` |

A ring plus two crossed lines is a gunsight whatever the caption calls it.
The premise is that something turned up to help.

## The lockup

Redesigned 2026-09-08, after Ben Bos. `gzlogo.py` draws the logo from data,
and the opening and the segment transition cards both take it from there:

    GROUND   small, tracked to the width of the word below, bone. The place.
    ZERØ     large, marigold. The zero is a ring and a bar on the face's own
             grid — three units of stroke, the stem weight of the letters,
             forty-five degrees, ends cut square. A slashed zero: this is a
             nought, not an O. The baguette survives as a proportion, not a
             picture.

Flat. No bevel, no shadow, no keyline, no shine. The face is a 14x16 heavy
grotesque with one-pixel chamfers, squarer than the rounded 16x18 it
replaces, so it holds at the 107-px rail sizes the channel airs at.

Two other readings are kept behind `GZ_LOGO_VARIANT`: `slash`, the same
lockup with a top-lit bevel and the loaf drawn as a loaf, and `orbit`, the
ring painted through the wormhole. Neither is the logo.
`python3 gzlogo.py OUT.png --variant …` renders any of them for review.

Under the title, the horizon: one rule with a dent where it went in.

## Why it looks like that

**320x240, doubled.** The logical canvas is 4:3 with square pixels, scaled to
640x480 with `neighbor`. 640x480 is what the other station cards are authored
at, and a 4:3 item pillarboxes into the channel's 854x480 **exactly inside the
on-air rails**, so no part of this is ever drawn under the up-next strip or the
weather card.

**16-bit means specific things.** Per-scanline gradients — HDMA tables — for
the signal field, the deep field, the night sky, the lake and the plates
behind the claim and the lockup; **colour math**, so the transmission, the
answering star, the ring, the descent, the impact and the light behind the
lockup all add rather than replace; depth planes separated by *contrast*
(the three ranges are three values of the same blue, no outlines); and type
cut from a ramp with a keyline. `gzpal.py` holds the ramps and stop lists.

**One bitmap face for the captions.** The 6x7 uppercase face in an 8x8 cell,
at 2x, shaded row by row. The display face lives with the lockup.

**Stars are a hash, not a random source.** Positions and depths come from an
integer hash of the star's index, so the field is the same field every build.

## The score

`gzaudio.py` synthesises an SPC700: wavetable voices — bass, lead, brass,
strings, bell — each with an ADSR envelope, equal-power stereo pan, an
optional detuned second voice for chorus, and an echo send. The mixdown runs
a delay line with feedback and a one-pole lowpass in the loop, so repeats get
darker rather than only quieter.

**Slow and grave, with no tempo.** A drone on A under everything (bass A1,
strings E2 and A2, attacks of four to nine seconds). A pulse once a second
while the signal is leaving, fading as it thins. Strings on A minor, then F,
with sparse bells. The ring is a swell — three string voices with a
four-and-a-half-second attack and a G in the bass. The descent holds an E; the
impact is a kick, a sweep from 72 to 24 Hz and a short dark burst, then
almost nothing: the drone and one bell a long way off. The claim gets A minor
and three bells. The lockup closes on an **open fifth** — A and E across five
octaves, no third at all, because the story does not resolve sweetly.

The 168 BPM chip score this replaces is in the repository's history. Nothing
of it survives except the instruments and the ending's interval.

### Verification without ears

`test_audio.py` proves three things, each with a negative control, and
`build.sh` runs it before rendering anything:

| Check | How |
|---|---|
| The echo unit works | one note with a full send must repeat at 0.30 s intervals, decaying — and must **not** repeat with the send at zero |
| The pan law works | hard left >20x louder in L than R and vice versa; centre equal |
| Voices play the right notes | Goertzel at the note against both neighbouring semitones, with the window **sized to the frequency** |

The ending is checked the same way rather than by ear: neither C nor C# may
be anywhere near the level of the A and the E in the last 1.2 s. It measures
**22:1**.

## Putting it on air

**Installing the file airs nothing.** It lands in `opens/groundzero/`, which no
pool selects, and it stays inert until the schedule names it. That is
deliberate — `cards/groundzero/` is the pool `coming_soon_gnd` *shuffles* to
pad the hour, and an opening shuffled into the middle of its own slot is worse
than no opening at all.

1. **Install and rescan.** `./build.sh --install` (from x), then let ErsatzTV
   rescan `/media` (it does so on its own within six hours) or trigger it from
   the UI. Do **not** `UPDATE LibraryPath SET LastScan = NULL` on the live DB.
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
   ```

   then regenerate `channel-z0.yml` (`--start-day thursday`) and redeploy the
   playout. Both the 19:00 slot and the 22:00 encore take the same change.

Do steps 2 and 3 **after** the rescan has actually found the file. An empty
content pool is skipped in silence — it does not error, it leaves a hole.

> **Note.** The COMING SOON card in `playout/cards/ground-zero.html` still
> carries the old reticle mark. It is a separate artefact, currently on air,
> and it was left alone rather than re-rendered under a live slot — but it no
> longer matches the programme's identity and should be reworked to the ZERØ
> lockup above.

---

<table>
<tr>
<td><b>DOC NO. RL-Z0-GND-B</b><br>REV. F · EST. 2026</td>
<td align="right"><b>PARRY ♻ RIPOSTE ♻ RECYCLE ♻ REPEAT</b><br>Riposte Laboratories Inc.</td>
</tr>
</table>
