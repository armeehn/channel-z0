// Emit one specimen's geometry as JSON on stdout.
//
// The renderer draws the ink from THIS, rather than from its own copy of the
// turtle, so the strokes on screen and the motion vectors ffedit lays over
// them come from the same eleven lines of JavaScript. Two implementations of
// the same L-system would drift apart the first time one was tuned.
//
//   qjs lsys-emit.js <width> <height>
//
// The specimen is imported as ./_specimen.js -- the renderer copies the file
// it is about to hand ffedit into place under that name. A static import is
// deliberate: it fails loudly if the copy is missing, where a dynamic one
// would resolve to whatever happened to be next to the script.
import { SYS, expand, walk } from "./_specimen.js";

const W = parseInt(scriptArgs[1], 10);
const H = parseInt(scriptArgs[2], 10);
const LIMIT = 200000;   // the string is for display; a fern is much longer

const s = expand();
const seg = walk(W, H);
const q = (v) => Math.round(v * 4) / 4;

console.log(JSON.stringify({
  sys: SYS,
  symbols: s.length,
  drawn: seg.length,
  string: s.slice(0, LIMIT),
  truncated: s.length > LIMIT,
  seg: seg.map((v) => [q(v[0]), q(v[1]), q(v[2]), q(v[3]),
                       Math.round(v[4] * 100000) / 100000]),
}));
