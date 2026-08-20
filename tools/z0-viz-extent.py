#!/usr/bin/env python3
"""Lowest text row on each backplate, in 640x480 card space.

The analyser must start BELOW every card's text. The title/artist shrink-to-fit
in render-music.mjs bounds the TITLE box, but a long artist credit still wraps
to a second line, so the safe start point is a measurement, not a guess.
"""
import os, sys
from PIL import Image

cards = sys.argv[1]
worst = []
for name in sorted(os.listdir(cards)):
    if not name.endswith('.png'):
        continue
    im = Image.open(os.path.join(cards, name)).convert('L')
    w, h = im.size
    scale = h / 480.0
    px = im.load()
    # Scan only the analyser's own x span (40..600 in card space). Scanning the
    # full width instead reports y=367 for every card, which is not text at all
    # -- it is the decorative .corner.bl bracket at x 18..31, which the analyser
    # never reaches.
    x0, x1 = int(40 * scale), int(600 * scale)
    low = 0
    for y in range(int(430 * scale), int(60 * scale), -1):
        row = max(px[x, y] for x in range(x0, x1, 3))
        if row > 110:
            low = y / scale
            break
    worst.append((low, name))
worst.sort(reverse=True)
print('lowest text row (640x480 space), worst 6:')
for low, name in worst[:6]:
    print('  y=%6.1f  %s' % (low, name))
print('\nMAX = %.1f  -> analyser may start at y >= %d' % (worst[0][0], int(worst[0][0]) + 10))
