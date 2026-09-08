# GROUND ZERO — opening titles

**DOC NO. RL-Z0-GND-B · REV. E**

A 60-second opening title sequence for the nightly GROUND ZERO slot, in the
grammar of the *Mega Man X* intros and telling the programme's own story: a
distress signal leaves Earth, someone a long way off answers it, comes through
a wormhole, and puts her ship into a hillside in the Okanagan where nobody
sees her land. She then goes and asks people what they are doing, holding a
baguette.

Everything on screen is generated: two hand-authored bitmap fonts, two
procedurally-built sprites, a palette of ramps, and an SPC700-style score. No
fonts, no samples, no stock art, no network.

| | |
|---|---|
| Source | `tools/z0-gz-open/` |
| Build | `tools/z0-gz-open/build.sh [--install]` |
| Output | `GROUND ZERO - OPENING TITLES.mp4` — 60.0 s, 640x480, 30 fps, H.264 + AAC |
| Installs to | `/mnt/main-data/channelz0/opens/groundzero/` on vile |
| Tags | `media`, `opens`, `groundzero` |

---

## The beats

| Frames | Time | Beat |
|---|---|---|
| 0–134 | 0:00 | **Sting.** `RIPOSTE LABORATORIES INC.` types in over ticks, flashes, drops the tri-band. A four-note chime resolving to C major. |
| 135–554 | 0:04.5 | **Prologue crawl.** Fourteen lines over a deep field, with the signal itself arriving from off frame right. Ends on `TO COME HOME.` |
| 555–764 | 0:18.5 | **Deep space.** Earth, small and far off, throwing out arcs that are not addressed to anyone. Her ship drifts in from frame left, and at the halfway mark the plume doubles and she starts closing. |
| 765–944 | 0:25.5 | **The wormhole.** A tunnel of rings in light blue, white and pink. |
| 945–1184 | 0:31.5 | **The landing.** A fireball down the diagonal, an impact, and then the Okanagan: two ranges, the lake, the moon — and the ship nose-down in the hillside, burning, with Sasha standing on the near shore. `NOBODY SAW HER LAND`. |
| 1185–1304 | 0:39.5 | **Her face.** A push-in. She blinks and holds. She does not smile — she has just been brought down a long way from home. |
| 1305–1454 | 0:43.5 | **SASHA ZERO.** The name in the display face — SASHA in bone, ZERO in marigold — and her posting. |
| 1455–1664 | 0:48.5 | **Logo.** `GROUND` drops, `ZERØ` arrives from the right, the frame judders, and the horizon draws in with the landing dent under the zero. |
| 1665–1799 | 0:55.5 | **Attract.** `PRESS START`, the transmission times, the copyright. |

The prologue is played completely straight. What it is grave about is a local
news bulletin.

## Nothing here is a crosshair

An earlier pass built the whole identity around a reticle — the O of `ZERO`
*was* one, the crawl's mark was one, and the strapline read `EPICENTRE`. All of
it is gone, deliberately:

| Was | Is |
|---|---|
| The O of ZERO as a targeting reticle | the zero of ZERØ: a ring and ONE bar, the slashed zero — `test_logo.py` proves the midlines inside the ring are empty |
| A reticle holding station in the crawl | a **transmission bloom**: concentric *arcs*, opening one way |
| `DESIG. RL-Z0-GND · EPICENTRE` | `DESIG. RL-Z0-GND · LANDING SITE` |

`signal_arcs()` draws arcs and never rings-with-a-cross, and the docstring says
why: a ring plus two crossed lines is a gunsight whatever the caption calls it.
The premise is that she turned up to help.

## The lockup

Redesigned 2026-09-08, after Ben Bos. The first identity was a ten-stop chrome
pastiche of the *Mega Man X* title card: it said "16-bit" and nothing else.
`gzlogo.py` now draws the logo from data, and the opening, the name card and
the segment transition cards all take it from there:

    GROUND   small, tracked to the width of the word below, bone. The place.
    ZERØ     large, marigold. The zero is a ring and a bar on the face's own
             grid — three units of stroke, the stem weight of the letters,
             forty-five degrees, ends cut square. A slashed zero: this is a
             nought, not an O. The baguette survives as a proportion, not a
             picture.

Flat. No bevel, no shadow, no keyline, no shine (the judder stays; gloss on a
flat mark is the wrong decade). The face is new too: a 14x16 heavy grotesque
with one-pixel chamfers, squarer than the rounded 16x18 it replaces, so it
holds at the 107-px rail sizes the channel airs at. Eleven glyphs — the ones
GROUND ZERO and SASHA need — and nothing else.

Two other readings are kept behind `GZ_LOGO_VARIANT`: `slash`, the same
lockup with a top-lit bevel and the loaf drawn as a loaf (crust, scores,
tips), and `orbit`, the ring painted through the wormhole. Neither is the
logo. `python3 gzlogo.py OUT.png --variant …` renders any of them for review.

Under the title, the horizon: one rule with a dent where the ship went in,
and the signal still travelling along the ground — it drops out over the
hole.

## Sasha Zero

Built on **Zero from Mega Man Zero**: the enormous ponytail, the crested helmet
with a gem set in the brow, gems on the shoulders and knees, red armour with
gold trim over a dark bodysuit, and a slim long-legged build.

Three things are hers rather than his. The ponytail is **pale blue with a pink
streak** instead of blonde; the gems are the station's **teal** instead of
green; and what she carries at her side — in the hand and at the angle Zero
carries the Z-Saber — is a **baguette**. It is the microphone. It has its own
colour ramp and three score marks because it has to read as bread at twelve
pixels.

The gold is Channel Z0's marigold, so the reference and the brand land on the
same colour and neither has to give way.

The wormhole is light blue, white and pink. It is the only place in the
sequence those three colours sit together, and nothing else needs to say it.

**The close-up wears the helmet too.** It did not, for one pass — bare hair in
the close-up while the sprite wore a crested helmet — which is the kind of
continuity error that only shows up when you put the two shots side by side.
The dome there is built as a **mask with the face opening subtracted**, not as
a filled ellipse: filled, it covered her eyes.

## The vessel

Not a rocket. No nose cone, no fins, no engine bell. A ribbed shell tapering
forward, a membrane along the back, a lit core showing through, and filaments
trailing behind it — something grown, that came a long way and did not survive
the arrival intact.

What follows from that is the rest of the tone: the wake is **bioluminescent**
rather than burned, the entry down the diagonal is cold white and teal rather
than a fireball, and what leaks out of the break at the crash site is the same
cold light the core showed in transit, guttering. Nothing aboard was on fire.

## Why it looks like that

**320x240, doubled.** The logical canvas is 4:3 with square pixels, scaled to
640x480 with `neighbor`. 640x480 is what the other station cards are authored
at, and a 4:3 item pillarboxes into the channel's 854x480 **exactly inside the
on-air rails**, so no part of this is ever drawn under the up-next strip or the
weather card.

**16-bit means specific things**, and each is a capability the 8-bit pass
(commit `c392ec2`) did not have: per-scanline gradients — HDMA tables — instead
of ordered dither; **colour math**, so the moon, the signal, the engine, the
fireball, the wormhole and the logo bloom all add rather than replace; depth
planes separated by *contrast*; shaded sprites lit from one direction; and a
flat, one-weight lockup for the display face (below).

**Ramps, not a fixed palette.** `gzpal.py` holds light-to-dark ramps and
gradient stop lists. Sprites index the ramps by position — highlight edge,
body, shadow edge — so one `shade()` call lights every part of a figure from
the same direction. Lighting a sprite part-by-part is how you get a character
lit from four directions at once.

**Two bitmap fonts, hand-authored.** A 6x7 uppercase face in an 8x8 cell for
all the type, and a 16x18 heavy face for the letters `GROUND ZERO` and
`SASHA ZERO` need.

## The score

`gzaudio.py` synthesises an SPC700: wavetable voices — slap bass, lead, brass,
strings, bell — each with an ADSR envelope, equal-power stereo pan, an optional
detuned second voice for chorus, and an echo send. The mixdown runs a delay
line with feedback and a one-pole lowpass in the loop, so repeats get darker
rather than only quieter.

**Driving but grave — the Mega Man *Zero* register** rather than classic Mega
Man. Those games are fast and heavy at the same time, and that is the target:
168 BPM and eighth-note bass keep the drive, while the loop turns on an E major
dominant and a Phrygian Bb instead of the bright C and G it used to, and the
piece ends on an **open fifth** — A and E, no third at all.

It went through both extremes to get here: a D-minor dirge at 150 BPM that felt
like a warning, then a Picardy third that resolved too sweetly for what the
story is.

The quiet bar is deliberate: everything stops for her face except a pad and a
bell. It is where the sequence stops being about a spaceship.

### Verification without ears

`test_audio.py` proves three things, each with a negative control, and
`build.sh` runs it before rendering anything:

| Check | How |
|---|---|
| The echo unit works | one note with a full send must repeat at 0.30 s intervals, decaying — and must **not** repeat with the send at zero |
| The pan law works | hard left >20x louder in L than R and vice versa; centre equal. An earlier pan law clamped on the near side and could never move a voice more than 2 dB — the mix measured 0.04 wide, i.e. mono |
| Voices play the right notes | Goertzel at the note against both neighbouring semitones, with the window **sized to the frequency** — at D2 a semitone is 4.4 Hz and a fixed 8192-sample window resolves only 5.9 Hz |

The ending is checked the same way rather than by ear. The claim is now an
*interval*, which is the right shape for the test: neither C nor C# may be
anywhere near the level of the A and the E. It measures **28:1**, so the final
chord is an open fifth and not a triad of either flavour.

`check_fits()` refuses to render if any fixed caption would run off the frame.
Two name-card values did exactly that, and the only symptom was a sentence
quietly missing its last few characters.

## Rebuilding

```sh
cd tools/z0-gz-open
./build.sh                       # renders to $GZ_WORK (default /var/tmp/z0-gz-open)
./build.sh --install             # ...and scp's it to vile
```

Needs `python3` with PIL, and `ffmpeg`. Takes about half a minute. Render
anywhere; run `--install` **from x** — LXC 111 has the checkout and the
toolchain but no SSH trust to vile, so the install half fails there with
`Host key verification failed`.

Fully deterministic — no seed, no clock, no network — so the master is
regenerated rather than archived, and `*.mp4` stays gitignored like every other
piece of station media.

```sh
python3 make_frames.py /tmp/stills --stills    # single frames, no encode
```

**Render stills and look at them.** Eight passes have been wrong here in ways no
code review would show: a black figure on a black ground (the near plane must
be the darkest thing in the frame); a visor close-up that looked like a
flowerpot; three times a figure whose armour fused into one solid mass because
nothing that was not armour separated the plates; a face pitched under flat
quads that read as a tent; a jaw that tapered too far and read as a muzzle; and
a helmet dome filled rather than carved, which covered her eyes.

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
     - pad_until: '19:58'
       ...
   ```

   Then regenerate, deploy with `z0-day-align.py --redeploy`, and reset the
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
<td><b>DOC NO. RL-Z0-GND-B</b><br>REV. E · EST. 2026</td>
<td align="right"><b>PARRY ♻ RIPOSTE ♻ RECYCLE ♻ REPEAT</b><br>Riposte Laboratories Inc.</td>
</tr>
</table>
