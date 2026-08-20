"""Sprite masks for the GROUND ZERO opening.

The hero is authored as a SILHOUETTE plus two overlay masks rather than as a
full-colour sprite.  At 34 px tall a shaded figure turns to mud, and the shot
it appears in is backlit anyway — so the body is one flat dark value, the visor
is the only lit part, and a rim mask picks out the edge that faces the sky.
Lightning re-lights the rim without redrawing anything.

'#' is opaque, '.' is transparent.
"""

HERO_W, HERO_H = 20, 34

# Standing, feet planted, head turned very slightly to camera left, mic held
# down in the right hand — the pose every one of these intros ends on.
HERO_BODY = [
"........##..........",   # crest tip
".......####.........",
"......########......",
".....##########.....",
"....############....",
"....############....",
"....############....",
"....############....",
"....############....",
".....##########.....",
"......########......",
"....############....",   # shoulder line
"...##############...",
"..################..",
"..################..",
"..################..",
"..###############...",
"..##############....",
"..##############..#.",   # right hand starts to come away from body
"...#############.##.",
"...############..##.",
"...###########...##.",
"....##########...##.",
"....#########....##.",
"....#########....##.",
"....####.####.......",
"....####.####.......",
"....####.####.......",
"....####.####.......",
"...#####.#####......",
"...#####.#####......",
"..######.######.....",
"..######.######.....",
".#######.#######....",
]

# The visor.  One slit, and it is the only thing in the shot with its own light.
HERO_VISOR = [
"....................",
"....................",
"....................",
"....................",
"....................",
".....########.......",
".....########.......",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
"....................",
]

# Rim light: the left edge and the top of the helmet, i.e. the side facing the
# break in the cloud.  Kept as its own mask so a lightning frame can swap its
# colour from marigold to bone without touching the body.
HERO_RIM = [
"........##..........",
".......#............",
"......##............",
".....#..............",
"....#...............",
"....#...............",
"....#...............",
"....#...............",
"....#...............",
".....#..............",
"......#.............",
"....#...............",
"...#................",
"..#.................",
"..#.................",
"..#.................",
"..#.................",
"..#.................",
"..#.................",
"...#................",
"...#................",
"...#................",
"....#...............",
"....#...............",
"....#...............",
"....#...............",
"....#...............",
"....#...............",
"....#...............",
"...#................",
"...#................",
"..#.................",
"..#.................",
".#..................",
]

# The microphone in the down hand: a stick mic, because the joke only lands if
# you can tell what it is.  Drawn separately so it can sit outside the body box.
MIC = [
"##",
"##",
"##",
".#",
".#",
".#",
".#",
]
MIC_W, MIC_H = 2, 7


def mask(rows):
    return [[c == "#" for c in r] for r in rows]


def _check(name, rows, w, h):
    assert len(rows) == h, f"{name}: {len(rows)} rows, want {h}"
    for i, r in enumerate(rows):
        assert len(r) == w, f"{name}: row {i} is {len(r)} wide, want {w}"


_check("HERO_BODY", HERO_BODY, HERO_W, HERO_H)
_check("HERO_VISOR", HERO_VISOR, HERO_W, HERO_H)
_check("HERO_RIM", HERO_RIM, HERO_W, HERO_H)
_check("MIC", MIC, MIC_W, MIC_H)

BODY = mask(HERO_BODY)
VISOR = mask(HERO_VISOR)
RIM = mask(HERO_RIM)
MIC_M = mask(MIC)
