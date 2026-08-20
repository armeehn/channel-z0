# GROUND ZERO — opening titles

**DOC NO. RL-Z0-GND-B · REV. B**

A 60-second opening title sequence for the nightly GROUND ZERO slot, built as a
16-bit parody of the *Mega Man X* / *X2* / *X3* openings. Everything on screen
is generated: two hand-authored bitmap fonts, one procedurally-built sprite, a
palette of ramps, and an SPC700-style score. No fonts, no samples, no stock
art, no network.

| | |
|---|---|
| Source | `tools/z0-gz-open/` |
| Build | `tools/z0-gz-open/build.sh [--install]` |
| Output | `GROUND ZERO - OPENING TITLES.mp4` — 60.0 s, 640x480, 30 fps, H.264 + AAC |
| Installs to | `/mnt/main-data/channelz0/opens/groundzero/` on vile |
| Tags | `media`, `opens`, `groundzero` |
| Loudness | **-23.8 LUFS** integrated, true peak **-1.0 dBFS**, LRA 12.5 LU |

---

## The beats

The structure is lifted from the X openings and the timings from them too: a
publisher sting, a long prologue nobody asked for, a hero shot, a push-in, and
a logo that arrives harder than the material warrants.

| Frames | Time | Beat |
|---|---|---|
| 0–134 | 0:00 | **Sting.** `RIPOSTE LABORATORIES INC.` types in over ticks, flashes, and drops the tri-band. A four-note chime — the Capcom logo jingle, in D minor. |
| 135–794 | 0:04.5 | **Prologue crawl.** Twenty-six lines over a deep-field wash and three star planes, with the programme's reticle holding station off the right edge. Ends on `GROUND ZERO.` |
| 795–1094 | 0:26.5 | **The rooftop.** Kelowna at night in the rain — two mountain ranges, the lake, the bridge, a mast. A lone hardsuit on a parapet, lit by the moon. Two lightning strikes. |
| 1095–1244 | 0:36.5 | **Push-in.** The visor, cropped by the frame, scanlines travelling. It flares white on the cut. |
| 1245–1559 | 0:41.5 | **Logo.** `GROUND` drops, `ZERO` arrives from the right, the frame judders, the reticle takes the place of the final O, and a shine sweeps the chrome. |
| 1560–1799 | 0:52 | **Attract.** `PRESS START`, the transmission times, the copyright, the tri-band. |

The joke is the register, not the gags: the prologue is played completely
straight, and what it is grave about is a local news bulletin.

## It was 8-bit first, and the differences are specific

The first pass (commit `c392ec2`) was a 2A03 and a sixteen-colour palette.
"Make it 16-bit" is not a filter you apply — it is a different machine, and
each of these is a concrete capability the earlier one did not have:

| | 8-bit pass | 16-bit pass |
|---|---|---|
| Sky | three ordered-dither bands | a per-scanline gradient — an HDMA table, evaluated once per line |
| Layers | opaque, replace only | **colour math**: rain, cloud, moon glow, lightning, the logo bloom and the visor flare all add or blend |
| Depth | position only | three planes separated by *contrast* — atmospheric perspective on two mountain ranges |
| Hero | a flat silhouette + a rim mask | a shaded 36x58 sprite, one light direction, lit palette swapped for lightning |
| Logo | three flat bands of marigold | a ten-stop chrome ramp, specular rim, keyline, cast shadow, and a lean |
| Fades | quantised to six steps | smooth |
| Audio | 2 pulses + triangle + noise | wavetable voices with ADSR, stereo pan, detune chorus, and a feedback echo |

**Mega Man X is a 16-bit game**, so this pass is the faithful one. The 8-bit
version is kept in history rather than in the tree; `git show c392ec2` has it.

## Why it looks like that

**320x240, doubled.** The logical canvas is 320x240 — 4:3 with square pixels —
scaled to 640x480 with `neighbor`. 640x480 is what the other station cards are
authored at, and a 4:3 item pillarboxes into the channel's 854x480 **exactly
inside the on-air rails**, so no part of this is ever drawn under the up-next
strip or the weather card.

**Ramps, not a fixed palette.** `gzpal.py` holds light-to-dark ramps for
armour, undersuit, steel, visor, bone and chrome, plus gradient stop lists for
the sky and the lake. Sprites index the ramps by position — highlight edge,
body, shadow edge — so one `shade()` call lights every part of the figure from
the same direction. Lighting a sprite part-by-part is how you end up with a
character lit from four directions at once.

**Two bitmap fonts, hand-authored.** `gzfont.py` holds a 6x7 uppercase face in
an 8x8 cell for all the type, and a 16x18 heavy face for the eight letters
`GROUND ZERO` needs. A hinted TTF rendered small produces soft uneven stems
that read as *small text* rather than as tiles.

**The hero is a Bubblegum Crisis hardsuit** in station colours: rounded-square
pauldrons carried high and flared, a narrow waist, hip flares, chunky forearm
bracers, heavy boots, a full-face helmet with a crown fin, swept-back ear fins
and a wraparound visor. She is built from primitives rather than typed as
colour-keyed ASCII, which is what makes the shading consistent — and what made
it cheap to re-proportion her twice when the first passes fused into one orange
mass from the helmet to the bracers.

## The score

`gzaudio.py` synthesises an SPC700 rather than a 2A03: wavetable voices —
slap bass, lead, brass, strings, bell — each with an ADSR envelope, equal-power
stereo pan, optional detuned second voice for chorus, and an echo send. The
mixdown runs a real delay line with feedback and a one-pole lowpass in the
loop, so repeats get darker rather than only quieter. That echo is most of why
this era sounds the way it does.

Pure Python and `wave` — numpy is broken in LXC 111 — and wavetable lookup is
a table index and an add, which is what makes that affordable: the whole track
renders in ten seconds.

D minor throughout, 150 BPM. The bed under the crawl is a bass note, a string
pad and a bell arpeggio for eleven bars; the lead does not arrive until the
crawl is half read, because the text is the event. Drums enter on the rooftop,
the push-in narrows to one rising line and an accelerating snare roll, and the
logo lands on an orchestra hit.

### Verification without ears

`test_audio.py` proves three things, each with a negative control, because all
three have been wrong at some point and none is visible in a waveform:

| Check | How |
|---|---|
| The echo unit works | one note with a full send must repeat at 0.30 s intervals, decaying — and must **not** repeat with the send at zero |
| The pan law works | hard left must be >20x louder in L than R and vice versa; centre must be equal. The first pan law clamped to 1.0 on the near side and could never move a voice more than 2 dB — the whole mix measured 0.04 wide, i.e. mono |
| Voices play the right notes | Goertzel at the note against both neighbouring semitones. **Size the window to the frequency**: at D2 a semitone is 4.4 Hz and a fixed 8192-sample window resolves only 5.9 Hz, so the bass fails for arithmetic reasons and not musical ones |

`build.sh` runs them before it renders anything.

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

It is fully deterministic — no seed, no clock, no network — so the master is
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
content pool is skipped in silence — it does not error, it leaves a hole — so
naming `gz_open` before the item exists takes the top of the hour off the air
with nothing to show for it.

---

<table>
<tr>
<td><b>DOC NO. RL-Z0-GND-B</b><br>REV. B · EST. 2026</td>
<td align="right"><b>PARRY ♻ RIPOSTE ♻ RECYCLE ♻ REPEAT</b><br>Riposte Laboratories Inc.</td>
</tr>
</table>
