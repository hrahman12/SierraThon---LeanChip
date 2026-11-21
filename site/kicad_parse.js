/**
 * kicad_parse.js: read a KiCad 7 `.kicad_pcb` file in the browser (or in Node).
 *
 * Extraction only. `parseKicadPcb` returns exactly the data that `leancheck.board_data()`
 * (Python + KiCad's own pcbnew, in leanvsdfm/tools/leancheck.py) returns for the same file,
 * so the Lean checker judges an uploaded board the same way the command-line tool does.
 * There is no verdict logic in this file: no rule, no colour, no pass or fail.
 *
 * The arithmetic follows KiCad 7's own code paths (file parser, RotatePoint, PAD effective
 * shapes, EDA_SHAPE bounding boxes), in integer nanometres. `tools/test_kicad_parse.mjs`
 * compares the result with pcbnew for every board in the repository.
 *
 *   parseKicadPcb(text, models, warnings?) -> { fps, parts, outline, n, thickness_nm }
 *   toProtocol(d, knobs?, dni?)            -> text for the `leanchip` binary (= leancheck.protocol)
 *
 * `models` is the "models" object of leanvsdfm/models3d/bbox.json (model base name ->
 * { min: [x, y, z], max: [x, y, z] } in nm). `warnings`, if given, is an array that receives
 * a line for every construct that is read on a best-effort basis (see the end of the file).
 */

// ---------------------------------------------------------------------------------------------
// KiCad number handling
// ---------------------------------------------------------------------------------------------

const IU_PER_MM = 1e6;                         // pcbIUScale: 1 nm
const INT_LIMIT = 2147483647 * 0.7071;         // PCB_PARSER::parseBoardUnits clamp
const NUMBER_RE = /^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/;

const nz = (v) => (v === 0 ? 0 : v);           // never let -0 out

/** KiCad's KiROUND: round half away from zero. */
function kiround(v) {
  return nz(Math.trunc(v < 0 ? v - 0.5 : v + 0.5));
}

/** PCB_PARSER::parseBoardUnits: a decimal mm string to integer nm, with the same double maths. */
function mmToIU(s) {
  let v = parseFloat(s) * IU_PER_MM;
  if (Number.isNaN(v)) throw new Error(`not a number: ${JSON.stringify(s)}`);
  if (v < -INT_LIMIT) v = -INT_LIMIT;
  else if (v > INT_LIMIT) v = INT_LIMIT;
  return kiround(v);
}

/** C++ integer division (truncates toward zero). */
const idiv = (a, b) => nz(Math.trunc(a / b));

const isNumber = (t) => typeof t === 'string' && NUMBER_RE.test(t);

// ---------------------------------------------------------------------------------------------
// Angles and rotation (EDA_ANGLE, RotatePoint)
// ---------------------------------------------------------------------------------------------

/** EDA_ANGLE::Normalize: into [0, 360). */
function norm360(a) {
  while (a < 0) a += 360.0;
  while (a >= 360.0) a -= 360.0;
  return a;
}

/** EDA_ANGLE::Normalize180: into (-180, 180]. */
function norm180(a) {
  while (a <= -180.0) a += 360.0;
  while (a > 180.0) a -= 360.0;
  return a;
}

const DEG2RAD = Math.PI / 180.0;

function sinDeg(a) {   // EDA_ANGLE::Sin
  if (a === 0 || a === 180) return 0.0;
  if (a === 45 || a === 135) return Math.SQRT1_2;
  if (a === 225 || a === 315) return -Math.SQRT1_2;
  if (a === 90) return 1.0;
  if (a === 270) return -1.0;
  return Math.sin(a * DEG2RAD);
}

function cosDeg(a) {   // EDA_ANGLE::Cos
  if (a === 0) return 1.0;
  if (a === 180) return -1.0;
  if (a === 90 || a === 270) return 0.0;
  if (a === 45 || a === 315) return Math.SQRT1_2;
  if (a === 135 || a === 225) return -Math.SQRT1_2;
  return Math.cos(a * DEG2RAD);
}

/** KiCad's RotatePoint (y axis down, positive angle = counter-clockwise on screen). */
function rotate(p, angleDeg) {
  const a = norm360(angleDeg);
  const x = p[0], y = p[1];
  if (a === 0) return [x, y];
  if (a === 90) return [y, nz(-x)];
  if (a === 180) return [nz(-x), nz(-y)];
  if (a === 270) return [nz(-y), x];
  const s = sinDeg(a), c = cosDeg(a);
  return [kiround(y * s + x * c), kiround(y * c - x * s)];
}

const add = (p, q) => [p[0] + q[0], p[1] + q[1]];
const sub = (p, q) => [p[0] - q[0], p[1] - q[1]];
const isCardinal = (a) => { const n = norm360(a); return n === 0 || n === 90 || n === 180 || n === 270; };

/** GetLineLength, exact on the axes (where a circle's "end" point normally is). */
function lineLength(p, q) {
  const dx = Math.abs(p[0] - q[0]), dy = Math.abs(p[1] - q[1]);
  if (dy === 0) return dx;
  if (dx === 0) return dy;
  return Math.hypot(dx, dy);
}

// ---------------------------------------------------------------------------------------------
// Boxes (BOX2I)
// ---------------------------------------------------------------------------------------------

class Box {
  constructor() { this.init = false; this.x0 = 0; this.y0 = 0; this.x1 = 0; this.y1 = 0; }
  static ofPoints(pts) { const b = new Box(); for (const p of pts) b.point(p); return b; }
  point(p) { return this.rect(p[0], p[1], p[0], p[1]); }
  rect(x0, y0, x1, y1) {
    const ax0 = Math.min(x0, x1), ay0 = Math.min(y0, y1), ax1 = Math.max(x0, x1), ay1 = Math.max(y0, y1);
    if (!this.init) { this.init = true; this.x0 = ax0; this.y0 = ay0; this.x1 = ax1; this.y1 = ay1; return this; }
    this.x0 = Math.min(this.x0, ax0); this.y0 = Math.min(this.y0, ay0);
    this.x1 = Math.max(this.x1, ax1); this.y1 = Math.max(this.y1, ay1);
    return this;
  }
  merge(b) { return b.init ? this.rect(b.x0, b.y0, b.x1, b.y1) : this; }
  inflate(d) { this.x0 -= d; this.y0 -= d; this.x1 += d; this.y1 += d; return this; }
}

/** SHAPE_SEGMENT::BBox: the end points, grown by (width + 1) / 2. */
const segmentBox = (a, b, width) => Box.ofPoints([a, b]).inflate(idiv(width + 1, 2));

// ---------------------------------------------------------------------------------------------
// S-expressions
// ---------------------------------------------------------------------------------------------

const ESCAPES = { n: '\n', r: '\r', t: '\t', a: '\x07', b: '\b', f: '\f', v: '\v' };

/** A KiCad file as nested arrays of strings: (a b (c "d")) -> ['a', 'b', ['c', 'd']]. */
function parseSexpr(text) {
  const n = text.length;
  const stack = [];
  let cur = null, root = null, i = 0;
  while (i < n) {
    const c = text.charCodeAt(i);
    if (c === 40) {                                   // (
      const list = [];
      if (cur) cur.push(list);
      stack.push(cur);
      cur = list;
      i++;
    } else if (c === 41) {                            // )
      if (!cur) throw new Error(`unbalanced ")" at offset ${i}`);
      const done = cur;
      cur = stack.pop();
      i++;
      if (!cur) { root = done; break; }
    } else if (c === 34) {                            // "
      let s = '';
      i++;
      for (;;) {
        if (i >= n) throw new Error('unterminated string');
        const ch = text[i];
        if (ch === '"') { i++; break; }
        if (ch === '\\' && i + 1 < n) {
          const e = text[i + 1];
          if (e === 'x') {
            const m = /^[0-9a-fA-F]{1,2}/.exec(text.slice(i + 2, i + 4));
            if (m) { s += String.fromCharCode(parseInt(m[0], 16)); i += 2 + m[0].length; continue; }
            s += 'x'; i += 2; continue;
          }
          if (e >= '0' && e <= '7') {
            const m = /^[0-7]{1,3}/.exec(text.slice(i + 1, i + 4));
            s += String.fromCharCode(parseInt(m[0], 8)); i += 1 + m[0].length; continue;
          }
          s += Object.prototype.hasOwnProperty.call(ESCAPES, e) ? ESCAPES[e] : e;
          i += 2;
          continue;
        }
        s += ch;
        i++;
      }
      if (!cur) throw new Error('text outside the top-level list');
      cur.push(s);
    } else if (c === 32 || c === 9 || c === 10 || c === 13) {
      i++;
    } else {
      const st = i;
      while (i < n) {
        const d = text.charCodeAt(i);
        if (d === 40 || d === 41 || d === 32 || d === 9 || d === 10 || d === 13 || d === 34) break;
        i++;
      }
      if (!cur) throw new Error('text outside the top-level list');
      cur.push(text.slice(st, i));
    }
  }
  if (!root) throw new Error('not a complete KiCad s-expression file');
  return root;
}

const kids = (node, name) => node.filter((c) => Array.isArray(c) && c[0] === name);
const kid = (node, name) => node.find((c) => Array.isArray(c) && c[0] === name);
const xy = (node) => [mmToIU(node[1]), mmToIU(node[2])];

/** Stroke width of a graphic: (stroke (width w) ...) or the older (width w). */
function strokeWidth(node) {
  const st = kid(node, 'stroke');
  const w = (st && kid(st, 'width')) || kid(node, 'width');
  return w ? mmToIU(w[1]) : 0;
}

// ---------------------------------------------------------------------------------------------
// Graphic shapes (EDA_SHAPE): footprint graphics and custom-pad primitives
// ---------------------------------------------------------------------------------------------

const SHAPE_KIND = { line: 'segment', rect: 'rect', circle: 'circle', arc: 'arc', poly: 'poly', curve: 'bezier' };

/** EDA_ANGLE( VECTOR2D ): direction of a vector in degrees, exact on the axes and diagonals. */
function vecAngle(x, y) {
  if (x === 0 && y === 0) return 0;
  if (y === 0) return x >= 0 ? 0.0 : -180.0;
  if (x === 0) return y >= 0 ? 90.0 : -90.0;
  if (x === y) return x >= 0 ? 45.0 : -135.0;
  if (x === -y) return x >= 0 ? -45.0 : 135.0;
  return Math.atan2(y, x) / DEG2RAD;
}

/**
 * KiCad's CalcArcCenter (libs/kimath/src/trigo.cpp): the centre of the arc through start, mid, end.
 * It is written out operation by operation, including the step that snaps the centre to a
 * multiple of 100 nm or 10 nm when that lies inside the propagated rounding error.
 */
function calcArcCenter(s, m, e) {
  const EPS = Number.EPSILON;
  let center;
  let yDelta21 = m[1] - s[1], xDelta21 = m[0] - s[0], yDelta32 = e[1] - m[1], xDelta32 = e[0] - m[0];
  if ((xDelta21 === 0 && yDelta32 === 0) || (yDelta21 === 0 && xDelta32 === 0)) {
    center = [(s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0];
  } else {
    if (xDelta21 === 0) xDelta21 = EPS;
    if (xDelta32 === 0) xDelta32 = -EPS;
    let aSlope = yDelta21 / xDelta21, bSlope = yDelta32 / xDelta32;
    const norm = (x, y) => Math.sqrt(x * x + y * y);
    const daSlope = aSlope * norm(0.5 / yDelta21, 0.5 / xDelta21);
    const dbSlope = bSlope * norm(0.5 / yDelta32, 0.5 / xDelta32);
    let done = false;
    if (aSlope === bSlope) {
      if (s[0] === e[0] && s[1] === e[1]) {                 // a full circle
        center = [(s[0] + m[0]) / 2.0, (s[1] + m[1]) / 2.0];
        done = true;
      } else {
        aSlope += EPS;
        bSlope -= EPS;
      }
    }
    if (!done) {
      if (aSlope === 0) aSlope = EPS;
      const R = Math.SQRT1_2;
      const abSlopeStartEndY = aSlope * bSlope * (s[1] - e[1]);
      const dabSlopeStartEndY = abSlopeStartEndY * Math.sqrt((daSlope / aSlope * daSlope / aSlope)
        + (dbSlope / bSlope * dbSlope / bSlope) + (R / (s[1] - e[1]) * R / (s[1] - e[1])));
      const bSlopeStartMidX = bSlope * (s[0] + m[0]);
      const dbSlopeStartMidX = bSlopeStartMidX * Math.sqrt((dbSlope / bSlope * dbSlope / bSlope)
        + (R / (s[0] + m[0]) * R / (s[0] + m[0])));
      const aSlopeMidEndX = aSlope * (m[0] + e[0]);
      const daSlopeMidEndX = aSlopeMidEndX * Math.sqrt((daSlope / aSlope * daSlope / aSlope)
        + (R / (m[0] + e[0]) * R / (m[0] + e[0])));
      const twiceBASlopeDiff = 2 * (bSlope - aSlope);
      const dtwiceBASlopeDiff = 2 * Math.sqrt(dbSlope * dbSlope + daSlope * daSlope);
      const centerNumeratorX = abSlopeStartEndY + bSlopeStartMidX - aSlopeMidEndX;
      const dCenterNumeratorX = Math.sqrt(dabSlopeStartEndY * dabSlopeStartEndY
        + dbSlopeStartMidX * dbSlopeStartMidX + daSlopeMidEndX * daSlopeMidEndX);
      const centerX = (abSlopeStartEndY + bSlopeStartMidX - aSlopeMidEndX) / twiceBASlopeDiff;
      const dCenterX = centerX * Math.sqrt((dCenterNumeratorX / centerNumeratorX * dCenterNumeratorX / centerNumeratorX)
        + (dtwiceBASlopeDiff / twiceBASlopeDiff * dtwiceBASlopeDiff / twiceBASlopeDiff));
      const centerNumeratorY = ((s[0] + m[0]) / 2.0 - centerX);
      const dCenterNumeratorY = Math.sqrt(1.0 / 8.0 + dCenterX * dCenterX);
      const centerFirstTerm = centerNumeratorY / aSlope;
      const dcenterFirstTermY = centerFirstTerm * Math.sqrt((dCenterNumeratorY / centerNumeratorY * dCenterNumeratorY / centerNumeratorY)
        + (daSlope / aSlope * daSlope / aSlope));
      const centerY = centerFirstTerm + (s[1] + m[1]) / 2.0;
      const dCenterY = Math.sqrt(dcenterFirstTermY * dcenterFirstTermY + 1.0 / 8.0);
      const r100x = Math.floor((centerX + 50.0) / 100.0) * 100.0, r100y = Math.floor((centerY + 50.0) / 100.0) * 100.0;
      const r10x = Math.floor((centerX + 5.0) / 10.0) * 10.0, r10y = Math.floor((centerY + 5.0) / 10.0) * 10.0;
      if (Math.abs(r100x - centerX) < dCenterX && Math.abs(r100y - centerY) < dCenterY) center = [r100x, r100y];
      else if (Math.abs(r10x - centerX) < dCenterX && Math.abs(r10y - centerY) < dCenterY) center = [r10x, r10y];
      else center = [centerX, centerY];
    }
  }
  const lim = 2147483647 / 2.0, lo = -2147483648 / 2.0;
  const clamp = (v) => (v < lo ? lo : v > lim ? lim : v);
  return [kiround(clamp(center[0])), kiround(clamp(center[1]))];
}

/**
 * Read one graphic in its own (unrotated) coordinates.
 * `prefix` is "fp_" for footprint graphics and "gr_" for custom-pad primitives.
 */
function readShape(node, prefix, warnings, where) {
  const type = SHAPE_KIND[node[0].slice(prefix.length)];
  if (!type) return null;
  const layerNode = kid(node, 'layer');
  const g = { type, layer: layerNode ? layerNode[1] : '', width: strokeWidth(node), filled: false,
              start: [0, 0], end: [0, 0], center: [0, 0], c1: [0, 0], c2: [0, 0], pts: [] };
  const fill = kid(node, 'fill');
  if (fill) g.filled = fill[1] === 'yes' || fill[1] === 'solid';
  else if (g.width === 0 && (type === 'rect' || type === 'circle' || type === 'poly')) g.filled = true;
  else if (type === 'poly' && g.layer !== 'Edge.Cuts') g.filled = true;
  const start = kid(node, 'start'), end = kid(node, 'end'), center = kid(node, 'center'), mid = kid(node, 'mid');
  if (type === 'circle') {
    if (center) g.start = xy(center);
    if (end) g.end = xy(end);
  } else if (type === 'arc') {
    if (mid && start && end) {
      g.start = xy(start); g.end = xy(end); g.center = calcArcCenter(g.start, xy(mid), g.end);
    } else if (start && end) {                     // KiCad 5: (start = centre) (end = arc start) (angle a)
      g.center = xy(start); g.start = xy(end);
      const ang = kid(node, 'angle');
      g.end = add(g.center, rotate(sub(g.start, g.center), ang ? -parseFloat(ang[1]) : 0));
    }
  } else if (type === 'poly' || type === 'bezier') {
    const pts = kid(node, 'pts');
    if (pts) g.pts = kids(pts, 'xy').map(xy);
    if (type === 'bezier') {
      if (g.pts.length === 4) { g.start = g.pts[0]; g.c1 = g.pts[1]; g.c2 = g.pts[2]; g.end = g.pts[3]; }
      g.approx = 'curve (control-point box)';
    } else if (pts && kids(pts, 'arc').length) {
      g.approx = 'polygon with arc edges (arc edges ignored)';
    }
  } else {
    if (start) g.start = xy(start);
    if (end) g.end = xy(end);
  }
  return g;
}

/** Place a shape: rotate by `angle` about the origin, then move by `pos` (FP_SHAPE::SetDrawCoord). */
function placeShape(g, angle, pos) {
  const t = (p) => add(rotate(p, angle), pos);
  return { ...g, start: t(g.start), end: t(g.end), center: t(g.center), c1: t(g.c1), c2: t(g.c2),
           pts: g.pts.map(t), angle, pos };
}

/** EDA_SHAPE::GetRadius. */
function shapeRadius(g) {
  const r = g.type === 'arc' ? lineLength(g.center, g.start) : lineLength(g.start, g.end);
  return Math.max(1, kiround(r));
}

/** EDA_SHAPE::GetRectCorners for a placed rectangle. */
function rectCorners(g) {
  let tl = g.start, br = g.end;
  const cardinal = isCardinal(g.angle);
  if (!cardinal) { tl = rotate(sub(tl, g.pos), -g.angle); br = rotate(sub(br, g.pos), -g.angle); }
  let pts = [tl, [br[0], tl[1]], br, [tl[0], br[1]]];
  if (!cardinal) pts = pts.map((p) => add(rotate(p, g.angle), g.pos));
  return pts;
}

/** Points that enclose a placed arc: its ends plus every axis extreme it crosses (EDA_SHAPE::computeArcBBox). */
function arcPoints(g) {
  const pts = [g.start, g.end];
  if (g.filled) pts.push(g.center);
  const r = shapeRadius(g);
  // CalcArcAngles
  let t1 = vecAngle(g.start[0] - g.center[0], g.start[1] - g.center[1]);
  let t2 = vecAngle(g.end[0] - g.center[0], g.end[1] - g.center[1]);
  if (t2 === t1) t2 = t1 + 360.0;
  if (t1 > t2) {
    if (t2 < 0) t2 = norm360(t2);
    else t1 = norm360(t1) - 360.0;
  }
  t1 = norm360(t1);
  t2 = norm360(t2);
  const hit = (q) => (t2 > t1 ? t1 < q && t2 > q : t1 < q || t2 > q);
  if (hit(0)) pts.push([g.center[0] + r, g.center[1]]);
  if (hit(90)) pts.push([g.center[0], g.center[1] + r]);
  if (hit(180)) pts.push([g.center[0] - r, g.center[1]]);
  if (hit(270)) pts.push([g.center[0], g.center[1] - r]);
  return pts;
}

/** EDA_SHAPE::getBoundingBox of a placed shape (includes half the line width). */
function shapeBox(g) {
  let b;
  if (g.type === 'rect') b = Box.ofPoints(rectCorners(g));
  else if (g.type === 'segment') b = Box.ofPoints([g.start, g.end]);
  else if (g.type === 'circle') b = Box.ofPoints([g.start]).inflate(shapeRadius(g));
  else if (g.type === 'arc') b = Box.ofPoints(arcPoints(g));
  else if (g.type === 'poly') b = Box.ofPoints(g.pts);
  else b = Box.ofPoints([g.start, g.c1, g.c2, g.end]);
  if (b.init) b.inflate(idiv(Math.max(0, g.width), 2));
  return b;
}

/** Bounding box of EDA_SHAPE::makeEffectiveShapes for a placed custom-pad primitive. */
function effectiveBox(g) {
  const grow = idiv(g.width + 1, 2);
  const edges = g.width > 0 || !g.filled;
  if (g.type === 'segment') return segmentBox(g.start, g.end, g.width);
  if (g.type === 'rect') return Box.ofPoints(rectCorners(g)).inflate(edges ? grow : 0);
  if (g.type === 'poly') return Box.ofPoints(g.pts).inflate(edges ? grow : 0);
  if (g.type === 'circle') {
    const b = Box.ofPoints([g.start]).inflate(shapeRadius(g));
    return edges ? b.inflate(idiv(g.width, 2)) : b;
  }
  if (g.type === 'arc') return Box.ofPoints(arcPoints(g)).inflate(idiv(g.width, 2));
  return Box.ofPoints([g.start, g.c1, g.c2, g.end]).inflate(grow);
}

// ---------------------------------------------------------------------------------------------
// Pads
// ---------------------------------------------------------------------------------------------

const DEFAULT_PAD_SIZE = 1524000;     // PAD constructor: 60 mil
const DEFAULT_PAD_DRILL = 762000;     //                  30 mil

function readPad(node, fp, nets, warnings) {
  const atoms = [];
  for (let i = 1; i < node.length && typeof node[i] === 'string'; i++) atoms.push(node[i]);
  const number = atoms.length ? atoms[0] : '';
  const attr = atoms[1] || 'thru_hole';
  const noHole = attr === 'smd' || attr === 'connect';
  const pad = { number, attr, shape: atoms[2] || 'circle', anchor: 'circle', pos0: [0, 0], orient: 0,
                size: [DEFAULT_PAD_SIZE, DEFAULT_PAD_SIZE],
                drill: noHole ? [0, 0] : [DEFAULT_PAD_DRILL, DEFAULT_PAD_DRILL], offset: [0, 0],
                rratio: 0.25, chamferRatio: 0, chamfers: 0, delta: [0, 0], net: '', primitives: [] };
  const where = `${fp.ref} pad ${JSON.stringify(number)}`;
  for (const c of node) {
    if (!Array.isArray(c)) continue;
    switch (c[0]) {
      case 'at':
        pad.pos0 = xy(c);
        if (isNumber(c[3])) pad.orient = norm360(parseFloat(c[3]));      // PAD::SetOrientation
        break;
      case 'size':
        pad.size = xy(c);
        break;
      case 'rect_delta':
        pad.delta = xy(c);
        break;
      case 'drill': {
        let haveWidth = false;
        const d = pad.drill.slice();
        for (let i = 1; i < c.length; i++) {
          const t = c[i];
          if (Array.isArray(t)) { if (t[0] === 'offset') pad.offset = xy(t); }
          else if (isNumber(t)) {
            if (!haveWidth) { d[0] = mmToIU(t); d[1] = d[0]; haveWidth = true; } else d[1] = mmToIU(t);
          }
        }
        pad.drill = noHole ? [0, 0] : d;
        break;
      }
      case 'roundrect_rratio':
        pad.rratio = Math.max(0.0, Math.min(parseFloat(c[1]), 0.5));
        break;
      case 'chamfer_ratio':
        pad.chamferRatio = Math.max(0.0, Math.min(parseFloat(c[1]), 0.5));
        if (pad.chamferRatio > 0) pad.shape = 'chamfered_rect';
        break;
      case 'chamfer':
        pad.chamfers = c.length - 1;
        if (pad.chamfers) pad.shape = 'chamfered_rect';
        break;
      case 'options': {
        const a = kid(c, 'anchor');
        if (a) pad.anchor = a[1] === 'rect' ? 'rect' : 'circle';
        break;
      }
      case 'primitives':
        for (const p of c) {
          if (!Array.isArray(p) || !p[0].startsWith('gr_')) continue;
          const g = readShape(p, 'gr_', warnings, where);
          if (!g) continue;
          pad.primitives.push(g);
          if (warnings && (g.approx || g.type === 'arc' || (g.type === 'circle' && (g.width > 0 || !g.filled)))) {
            warnings.push(`${where}: custom pad ${g.approx || g.type} primitive read on a best-effort basis`);
          }
        }
        break;
      case 'net': {
        const code = parseInt(c[1], 10);
        const name = c.length > 2 ? c[2] : '';
        if (code > 0 && nets.has(code) && nets.get(code) === name) pad.net = name;
        else if (code > 0 && warnings) warnings.push(`${where}: net ${code} ${JSON.stringify(name)} is not in the board's net table`);
        break;
      }
      default:
        break;
    }
  }
  if (pad.shape === 'chamfered_rect' && warnings) {
    warnings.push(`${where}: chamfered pad read on a best-effort basis (its full rectangle is used)`);
  }
  pad.pos = add(rotate(pad.pos0, fp.orient), fp.pos);                    // PCB_PARSER: pad position
  return pad;
}

/** PAD::GetBoundingBox: the box of the pad's effective shapes and of its hole (PAD::BuildEffectiveShapes). */
function padBox(pad) {
  const [sx, sy] = pad.size;
  const shapePos = (pad.offset[0] === 0 && pad.offset[1] === 0) ? pad.pos : add(pad.pos, rotate(pad.offset, pad.orient));
  const box = new Box();
  let eff = pad.shape === 'custom' ? pad.anchor : pad.shape;
  if (eff === 'oval' && sx === sy) eff = 'circle';
  if (eff === 'circle') {
    box.merge(Box.ofPoints([shapePos]).inflate(idiv(sx, 2)));
  } else if (eff === 'oval') {
    const half = [idiv(sx, 2), idiv(sy, 2)];
    const hw = Math.min(half[0], half[1]);
    const halfLen = rotate([half[0] - hw, half[1] - hw], pad.orient);
    box.merge(segmentBox(sub(shapePos, halfLen), add(shapePos, halfLen), hw * 2));
  } else {                                           // rect, trapezoid, roundrect, chamfered_rect
    const r = eff === 'roundrect' ? kiround(Math.min(sx, sy) * pad.rratio) : 0;
    const half = [idiv(sx, 2), idiv(sy, 2)];
    let td = [0, 0];
    let circle = false;
    if (r) {
      half[0] -= r; half[1] -= r;
      circle = half[0] === 0 && half[1] === 0;
    } else if (eff === 'trapezoid') {
      td = [idiv(pad.delta[0], 2), idiv(pad.delta[1], 2)];
    }
    if (circle) {
      box.merge(Box.ofPoints([shapePos]).inflate(r));
    } else {
      const corners = [[-half[0] - td[1], half[1] + td[0]], [half[0] + td[1], half[1] - td[0]],
                       [half[0] - td[1], -half[1] + td[0]], [-half[0] + td[1], -half[1] - td[0]]]
        .map((p) => add(rotate(p, pad.orient), shapePos));
      box.merge(Box.ofPoints(corners));
      if (r) for (let i = 0; i < 4; i++) box.merge(segmentBox(corners[i], corners[(i + 1) % 4], r * 2));
    }
  }
  if (pad.shape === 'custom') {
    for (const g of pad.primitives) box.merge(effectiveBox(placeShape(g, pad.orient, shapePos)));
  }
  // the hole (a zero-width point at the pad position when there is none)
  const hh = [idiv(pad.drill[0], 2), idiv(pad.drill[1], 2)];
  const hw = Math.min(hh[0], hh[1]);
  const hl = rotate([hh[0] - hw, hh[1] - hw], pad.orient);
  box.merge(segmentBox(sub(pad.pos, hl), add(pad.pos, hl), hw * 2));
  return box;
}

// ---------------------------------------------------------------------------------------------
// Footprints
// ---------------------------------------------------------------------------------------------

const FP_SHAPES = new Set(['fp_line', 'fp_rect', 'fp_circle', 'fp_arc', 'fp_poly', 'fp_curve']);

function readFootprint(node, nets, warnings) {
  const id = typeof node[1] === 'string' ? node[1] : '';
  const colon = id.indexOf(':');
  const fp = { lib: colon >= 0 ? id.slice(colon + 1) : id, ref: '', pos: [0, 0], orient: 0, shapes: [], pads: [], model: null };
  const at = kid(node, 'at');
  if (at) {
    fp.pos = xy(at);
    if (isNumber(at[3])) fp.orient = norm180(parseFloat(at[3]));          // FOOTPRINT::SetOrientation
  }
  for (const c of node) {
    if (!Array.isArray(c)) continue;
    if (c[0] === 'fp_text' && c[1] === 'reference') fp.ref = c[2];
    else if (c[0] === 'property' && c[1] === 'Reference' && !fp.ref) fp.ref = c[2];
  }
  for (const c of node) {
    if (!Array.isArray(c)) continue;
    if (FP_SHAPES.has(c[0])) {
      const g = readShape(c, 'fp_', warnings, `${fp.ref} ${c[0]}`);
      if (g) fp.shapes.push(placeShape(g, fp.orient, fp.pos));
    } else if (c[0] === 'pad') {
      fp.pads.push(readPad(c, fp, nets, warnings));
    } else if (c[0] === 'model' && !fp.model) {
      const m = { file: typeof c[1] === 'string' ? c[1] : '', offset: [0, 0, 0], scale: [1, 1, 1], rotate: [0, 0, 0] };
      for (const k of c) {
        if (!Array.isArray(k)) continue;
        const v = kid(k, 'xyz');
        if (!v) continue;
        const t = [parseFloat(v[1]), parseFloat(v[2]), parseFloat(v[3])];
        if (k[0] === 'offset') m.offset = t;
        else if (k[0] === 'at') m.offset = t.map((x) => x * Math.fround(25.4));   // pre-v5 files: inches
        else if (k[0] === 'scale') m.scale = t;
        else if (k[0] === 'rotate') m.rotate = t;
      }
      fp.model = m;
    }
  }
  return fp;
}

/** os.path.splitext(os.path.basename(path))[0] */
function modelBaseName(path) {
  const base = path.slice(path.lastIndexOf('/') + 1);
  const dot = base.lastIndexOf('.');
  if (dot < 0) return base;
  for (let i = 0; i < dot; i++) if (base[i] !== '.') return base.slice(0, dot);
  return base;
}

/** FOOTPRINT::GetBoundingBox(false, false): used only when a footprint has no courtyard. */
function footprintBox(fp) {
  const box = Box.ofPoints([fp.pos]).inflate(250000);
  for (const g of fp.shapes) box.merge(shapeBox(g));
  for (const p of fp.pads) box.merge(padBox(p));
  return box;
}

/** leancheck._courtyard: the courtyard rectangle from the graphics' real geometry. */
function courtyard(fp, warnings) {
  const xs = [], ys = [];
  for (const g of fp.shapes) {
    if (g.layer !== 'F.CrtYd' && g.layer !== 'B.CrtYd') continue;
    if (g.type === 'circle') {
      const r = shapeRadius(g);
      xs.push(g.start[0] - r, g.start[0] + r);
      ys.push(g.start[1] - r, g.start[1] + r);
    } else if (g.type === 'segment' || g.type === 'rect') {
      xs.push(g.start[0], g.end[0]);
      ys.push(g.start[1], g.end[1]);
    } else {
      const bb = shapeBox(g), w = Math.floor(g.width / 2);
      xs.push(bb.x0 + w, bb.x1 - w);
      ys.push(bb.y0 + w, bb.y1 - w);
      if (g.approx && warnings) warnings.push(`${fp.ref}: courtyard ${g.approx} read on a best-effort basis`);
    }
  }
  if (!xs.length) {
    const bb = footprintBox(fp);
    if (warnings) {
      warnings.push(`${fp.ref}: no courtyard drawn, so the footprint's bounding box is used (as leancheck does)`);
      for (const g of fp.shapes) if (g.approx) warnings.push(`${fp.ref}: ${g.approx} read on a best-effort basis`);
    }
    return [bb.x0, bb.y0, bb.x1, bb.y1];
  }
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// ---------------------------------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------------------------------

/** leancheck._outline: walk the Edge.Cuts line segments into one loop. */
function outlineLoop(root) {
  const segs = [];
  for (const d of root) {
    if (!Array.isArray(d) || d[0] !== 'gr_line') continue;
    const layer = kid(d, 'layer');
    if (!layer || layer[1] !== 'Edge.Cuts') continue;
    const s = kid(d, 'start'), e = kid(d, 'end');
    segs.push([s ? xy(s) : [0, 0], e ? xy(e) : [0, 0]]);
  }
  if (!segs.length) return [];
  const same = (p, q) => p[0] === q[0] && p[1] === q[1];
  const loop = [segs[0][0]];
  let cur = segs[0][1];
  const rest = segs.slice(1);
  while (rest.length && !same(cur, loop[0])) {
    loop.push(cur);
    let found = false;
    for (let i = 0; i < rest.length; i++) {
      const [a, b] = rest[i];
      if (same(a, cur) || same(b, cur)) {
        cur = same(a, cur) ? b : a;
        rest.splice(i, 1);
        found = true;
        break;
      }
    }
    if (!found) return [];
  }
  return loop;
}

/**
 * The board as plain data (nm), equal to `leancheck.board_data(path)`.
 * @param {string} text    contents of a KiCad 7 `.kicad_pcb`
 * @param {object} models  bbox.json "models": base name -> { min: [x, y, z], max: [x, y, z] }
 * @param {string[]} [warnings]  receives notes about constructs read on a best-effort basis
 */
export function parseKicadPcb(text, models, warnings) {
  const root = parseSexpr(text);
  if (root[0] !== 'kicad_pcb') throw new Error('not a KiCad board file (expected "(kicad_pcb ...")');
  const known = models || {};
  const version = kid(root, 'version');
  if (warnings && version && !/^2022/.test(version[1])) {
    warnings.push(`file format version ${version[1]}: this reader follows KiCad 7 (2022xxxx)`);
  }
  const nets = new Map();
  for (const c of kids(root, 'net')) nets.set(parseInt(c[1], 10), c.length > 2 ? c[2] : '');

  const footprints = [];
  for (const c of root) {
    if (Array.isArray(c) && (c[0] === 'footprint' || c[0] === 'module')) footprints.push(readFootprint(c, nets, warnings));
  }
  // Python: sorted(..., key=reference). Array.prototype.sort is stable, like sorted().
  footprints.sort((a, b) => (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0));

  const fps = [], parts = [];
  for (const fp of footprints) {
    const pads = [], px = [], py = [], drills = [];
    for (const p of fp.pads) {
      const bb = padBox(p);
      px.push(bb.x0, bb.x1);
      py.push(bb.y0, bb.y1);
      if (p.drill[0] > 0) drills.push(p.drill[1] > 0 ? Math.min(p.drill[0], p.drill[1]) : p.drill[0]);
      if (!p.number) continue;
      pads.push({ number: p.number, net: p.net, x: p.pos0[0], y: p.pos0[1], w: p.size[0], h: p.size[1] });
    }
    fps.push({ ref: fp.ref, lib: fp.lib, rot: nz(Math.trunc(fp.orient)), pads });

    let model = null, height = 0;
    if (fp.model) {
      const m = fp.model;
      const name = modelBaseName(m.file);
      const plain = [...m.offset, ...m.rotate].every((v) => Math.abs(v) < 1e-9) && m.scale.every((v) => Math.abs(v - 1) < 1e-9);
      if (Object.prototype.hasOwnProperty.call(known, name) && plain) {
        const mn = known[name].min, mx = known[name].max;
        model = [nz(Math.trunc(mn[0])), nz(Math.trunc(mn[1])), nz(Math.trunc(mx[0])), nz(Math.trunc(mx[1]))];
        height = mx[2];
      }
    }
    const near = Math.round(fp.orient);
    const rot = Math.abs(fp.orient - near) < 1e-6 ? nz(near) : 1;
    parts.push({
      ref: fp.ref, px: fp.pos[0], py: fp.pos[1], rot, court: courtyard(fp, warnings),
      pads: px.length ? [Math.min(...px), Math.min(...py), Math.max(...px), Math.max(...py)]
                      : [fp.pos[0], fp.pos[1], fp.pos[0], fp.pos[1]],
      model, height, min_drill: drills.length ? Math.min(...drills) : 0,
    });
  }

  const general = kid(root, 'general');
  const thick = general && kid(general, 'thickness');
  return { fps, parts, outline: outlineLoop(root), n: fps.length, thickness_nm: thick ? mmToIU(thick[1]) : 1600000 };
}

/** A whole board (and optional design-package knobs) as input for the `leanchip` binary: = leancheck.protocol. */
export function toProtocol(d, knobs, dni) {
  const lines = [];
  for (const [k, v] of Object.entries(knobs || {})) lines.push(`K\t${k}\t${v}`);
  for (const r of dni || []) lines.push(`D\t${r}`);
  lines.push(`B\tthickness\t${d.thickness_nm}`);
  for (const [x, y] of d.outline) lines.push(`O\t${x}\t${y}`);
  for (const f of d.fps) {
    lines.push(['F', f.ref, f.lib, String(f.rot)].join('\t'));
    for (const p of f.pads) lines.push(['P', p.number, p.net, p.x, p.y, p.w, p.h].join('\t'));
  }
  for (const t of d.parts) {
    const m = t.model;
    lines.push(['T', t.ref, t.px, t.py, t.rot, ...t.court, ...t.pads, m ? '1' : '0', ...(m || [0, 0, 0, 0]), t.height, t.min_drill].join('\t'));
  }
  return lines.join('\n') + '\n';
}

/*
 * What is exact and what is best effort
 *
 * Exact (same integer arithmetic as KiCad 7, checked against pcbnew by tools/test_kicad_parse.mjs):
 *   footprint position, rotation, reference and library name; pad number, net, local position
 *   and size; drills (round and oval); pad boxes for circle, oval, rect, roundrect and trapezoid
 *   pads, with pad offsets; courtyards drawn with lines, rectangles, circles and polygons;
 *   the Edge.Cuts loop; the board thickness; the first 3D model and its "plain" test.
 *
 * Best effort (a note is pushed to `warnings`): arcs and curves in a courtyard or in a custom
 *   pad, polygons with arc edges, and chamfered pads. Footprints at angles that are not a
 *   multiple of 90 degrees go through KiCad's sin/cos path; the Lean checker reports those
 *   as "rotation is not a right angle" anyway.
 */
