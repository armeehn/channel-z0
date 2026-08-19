// KOCH ISLAND  ·  CH 0 L-SYSTEM SPECIMEN 4/8
// Every edge grows a smaller copy of the
// whole coast. The perimeter never settles.
//
// This file is the whole program. qjs runs it
// to draw the ink; ffedit runs it again to
// bend the motion vectors that smear it. You
// are reading what made the picture beside it.

export const SYS = {
  name:    "KOCH ISLAND",
  caption: "a coastline of finite area",
  ink:     "#ff2d2d",
  axiom:   "F+F+F+F",
  rules:   { F: "F+F-F-FF+F+F-F" },
  angle:   90,  // degrees per + or -
  gens:    3,   // rewrites
  heading: 0,   // where the turtle starts
  push:    16,  // how hard ffedit shoves it
};
const RAD = Math.PI / 180;

// -- 1. rewrite: apply the rules to the axiom,
//    once per generation.
export function expand() {
  let s = SYS.axiom;
  for (let g = 0; g < SYS.gens; g++) {
    let out = "";
    for (const c of s) out += SYS.rules[c] || c;
    s = out;
  }
  return s;
}

// -- 2. walk: read the string as turtle orders.
//    F and G draw, f lifts the pen, + and - turn,
//    [ and ] push and pop the turtle.
export function walk(w, h) {
  const s = expand(), stack = [], seg = [];
  const turn = SYS.angle * RAD;
  let x = 0, y = 0, a = SYS.heading * RAD;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "F" || c === "G" || c === "f") {
      const nx = x + Math.cos(a);
      const ny = y + Math.sin(a);
      if (c !== "f")
        seg.push([x, y, nx, ny, i / s.length]);
      x = nx; y = ny;
    } else if (c === "+") { a += turn;
    } else if (c === "-") { a -= turn;
    } else if (c === "[") { stack.push([x, y, a]);
    } else if (c === "]") {
      const p = stack.pop();
      x = p[0]; y = p[1]; a = p[2];
    }
  }
  return fit(seg, w, h);
}

// -- 3. fit: the turtle works in its own units,
//    so centre the drawing in the frame.
function fit(seg, w, h) {
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const s of seg) {
    x0 = Math.min(x0, s[0], s[2]);
    x1 = Math.max(x1, s[0], s[2]);
    y0 = Math.min(y0, s[1], s[3]);
    y1 = Math.max(y1, s[1], s[3]);
  }
  const m = 26;
  const kx = (w - 2 * m) / (x1 - x0 || 1);
  const ky = (h - 2 * m) / (y1 - y0 || 1);
  const k = Math.min(kx, ky);
  const ox = (w - (x1 - x0) * k) / 2 - x0 * k;
  const oy = (h - (y1 - y0) * k) / 2 - y0 * k;
  for (const s of seg) {
    s[0] = s[0] * k + ox; s[1] = s[1] * k + oy;
    s[2] = s[2] * k + ox; s[3] = s[3] * k + oy;
  }
  return seg;
}

// -- 4. bake: hand every macroblock the heading
//    of the branch that crosses it, and the
//    moment the turtle drew that branch.
function bake(seg, C, R) {
  const f = new Array(C * R).fill(null);
  for (const s of seg) {
    const j = (s[0] / 16) | 0;
    const i = (s[1] / 16) | 0;
    if (i < 0 || i >= R) continue;
    if (j < 0 || j >= C) continue;
    const dx = s[2] - s[0], dy = s[3] - s[1];
    const m = Math.hypot(dx, dy) || 1;
    // A block at the frame edge must not fetch
    // from outside it: that decodes flat green.
    const d = Math.min(i, j, R - 1 - i, C - 1 - j);
    const e = d >= 3 ? 1 : d / 3;
    f[i * C + j] = [dx / m * e, dy / m * e, s[4]];
  }
  return f;
}

// -- 5. ffedit runs this file too. A wave of
//    motion travels the branches in the order
//    they were drawn, so the picture smears
//    along its own growth.
let F = null, n = 0, P = {};

export function setup(args) {
  args.features = [ "mv" ];
  P = args.params || {};
}

export function glitch_frame(frame) {
  const fwd = frame.mv && frame.mv.forward;
  if (!fwd) return;
  const R = fwd.length, C = fwd[0].length;
  if (F === null)
    F = bake(walk(C * 16, R * 16), C, R);
  // u: 0 as the turtle starts, 1 as it ends.
  const p = n++ * 100 / P.frames;
  const u = (p - P.t0) / (P.t1 - P.t0);
  const win = P.win / 100;
  for (let i = 0; i < R; i++) {
    for (let j = 0; j < C; j++) {
      if (fwd[i][j] == null) continue;
      const f = F[i * C + j];
      if (f === null || u < 0) {
        fwd[i][j] = MV(0, 0);
        continue;
      }
      // the wave, then a drift once it is past
      let g = 1 - Math.abs(f[2] - u) / win;
      g = g < 0 ? 0 : g;
      if (u > 1) {
        const r = (u - 1) * 4;
        const b = Math.min(P.bloom / 100, r);
        g = g > b ? g : b;
      }
      const s = g * SYS.push * P.trim / 1000;
      fwd[i][j] = MV(Math.round(f[0] * s),
                     Math.round(f[1] * s));
    }
  }
}
