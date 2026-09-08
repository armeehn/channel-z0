# Segment transitions — the cards between the parts of a show

Channel Z0's three originals — GROUND ZERO, LAB HOUR and the NEIGHBOURHOOD
DESK — are built from segments, and a segment needs a door. These are the
doors: four-second cards that say where the programme is going next, one per
segment, plus a matched pair for the advert break (`break-out` / `break-in`)
and, for GROUND ZERO, a closing tease. Generated wholly from code in
`tools/z0-transitions/`, from one manifest (`segments.json`), so a new
segment is a line of JSON and a rebuild.

Each show keeps its own grammar. The cards are furniture arriving before the
house: none of these shows has footage yet, and every segment card exists the
day the first segment does.

## The three grammars

**GROUND ZERO** — the 16-bit vocabulary of the opening title
(`docs/ground-zero-open.md`), 320x240 doubled to 640x480 with no
interpolation. A stage-select band slides in from the right, the ZERØ mark
lands from the left, the segment name types itself in the title's bitmap face
with a marigold block cursor, and the strap line follows. The station's
tri-band (pink, marigold, teal) holds the foot of the frame. A chip sting from
`gzaudio.py`: kick, crash, orchestra hit, a four-note brass phrase on the
segment's chord, a bell to close. Chords cycle Am, F, G, E, Dm by segment
number; breaks take Dm.

**LAB HOUR** — a drawing sheet. Bone paper wipes down over the ink with a
20 px drafting grid; a title block sits bottom-right the way a sheet carries
one (`RIPOSTE LABORATORIES · LAB HOUR` / `SEGMENT 02 OF 05` /
`SHEET RL-LAB-02 · REV A`). The segment name is revealed by a red cursor
sweeping across it, then **dimensioned**: a red dimension line with arrowheads
and extension lines gives the width of the word in millimetres at the sheet's
96 dpi. In this programme everything gets measured. Bells only.

**NEIGHBOURHOOD DESK** — an index card. It drops onto the desk with a little
overshoot and settles at three degrees, ruled the way an index card is ruled,
a red pushpin at the top. The segment name is rubber-stamped on it in station
red — the stamp comes in large and faint and lands solid, and its texture is
a hash of the pixel position rather than a random source, so the frames are
the same bytes every build. The strap line is typed underneath. A thud for the
card, a thud and a snap for the stamp, a tick per typed character.

All three are 640x480 (4:3, like every other station card — it pillarboxes
exactly inside the on-air rails), 30 fps, 4.000 s, H.264 + AAC 48 kHz stereo.
`build.sh` refuses any output that is not exactly that shape.

## The segments

| Show | Segments | Break pair | Close |
|---|---|---|---|
| GROUND ZERO | CONTACT · THE INTERVIEW · THE BAGUETTE TEST · FIELD NOTES · THE VERDICT | BACK IN A MOMENT / CONTACT RESUMED | NEXT CONTACT |
| LAB HOUR | THE BENCH · MATERIALS · THE BUILD · THE TEST · SHIP IT | BACK AFTER THIS / BACK AT THE BENCH | — |
| NEIGHBOURHOOD DESK | NOTICES · LOST & FOUND · EVENTS · FOR SALE · THE CASSEROLE | BACK AFTER THIS / THE DESK IS BACK | — |

Twenty-two cards. Every title and strap line has a width limit per grammar and
`check_manifest()` refuses to render past it — the 16-bit card has 12 cells
per title line and 27 for a strap at the text column, and a header that ran
to 30 lost its last word off the right edge in the first render.

## Building

```
tools/z0-transitions/build.sh                 # all 22, into /var/tmp/z0-transitions
tools/z0-transitions/build.sh labhour bench   # one
python3 tools/z0-transitions/transitions.py stills OUTDIR   # one review frame per card
```

Runs in LXC 111 (PIL + the JetBrains Mono TTFs + ffmpeg); about six seconds a
card. `test_transitions.py` runs first and is the CI job `titles`; its picture
checks for the two TTF grammars skip where no monospace face is installed.

## Putting them on air

**Installing the files airs nothing.** They land in
`/media/transitions/<show>/` on vile, a folder chain no pool selects. The NFO
sidecar lists that chain verbatim — `media`, `transitions`, `<show>` — because
the sidecar *replaces* folder tags and one that forgot a tag would drop the
file out of its pool in silence. `transitions` is a NEW tag: ErsatzTV needs
the search index rebuilt (`rm -rf /config/search-index` + restart, off-hours),
not just a rescan, before `tag:transitions` returns anything.

1. Stage from x (the only host vile trusts):
   `scp /var/tmp/z0-transitions/z0-tr-*.{mp4,nfo} root@10.0.1.222:/mnt/main-data/channelz0/transitions/<show>/`
   (one folder per show — the folder is the tag).
2. Rebuild the index, rescan, and confirm the count in the UI before touching
   the schedule.
3. Add a content key per show to `playout/_content.yml`:

   ```yaml
     - search:
       key: gz_transitions
       query: 'type:other_video AND tag:transitions AND tag:groundzero'
       order: shuffle
   ```

4. Book them **between segment files**, never padded: a four-second file
   under `pad_until` schedules hundreds of items. As a sequence in
   `_sequences.yml`, invoked directly, with `filler_kind` so the guide does
   not list them:

   ```yaml
     - key: gz_segment
       items:
         - count: 1
           content: gz_transitions
           filler_kind: preroll
   ```

   When the shows have segment files, the slot reads segment / `gz_segment` /
   segment / `advert_break` / segment. A specific card (the break pair, the
   close) wants its own key with `tag:` narrowed by title, or a per-card
   collection — the shuffle pool is for the numbered segments.

Regenerate `channel-z0.yml` with `--start-day thursday` and check main still
regenerates to itself before deploying.

## Related

`docs/ground-zero-open.md` (the lockup and the face the GROUND ZERO card
uses), `docs/intervals.md` (the other family of station furniture, and the
index-rebuild trap), `docs/programming.md` (the show bible these segments
extend).
