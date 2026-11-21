#!/usr/bin/env node
/**
 * Does the browser's KiCad reader agree with KiCad itself?
 *
 * For every board in pcb/ (and any extra board paths given on the command line) this compares
 *   site/kicad_parse.js   parseKicadPcb(text, models)      (what the website extracts)
 * with
 *   tools/dump_board_data.py -> leancheck.board_data(path)  (what KiCad's pcbnew extracts)
 * value by value, and compares toProtocol(...) with Python's leancheck.protocol(...) byte for
 * byte. Exit code 0 only if every board passes.
 *
 *     node tools/test_kicad_parse.mjs [more.kicad_pcb ...]
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const PYTHON = process.env.PYTHON || 'python3';
const BIG = { maxBuffer: 256 * 1024 * 1024 };

// site/ has no package.json, so load the browser module from its text (works on every Node version).
const source = readFileSync(resolve(ROOT, '..', 'site', 'kicad_parse.js'));
const { parseKicadPcb, toProtocol } = await import('data:text/javascript;base64,' + source.toString('base64'));
const models = JSON.parse(readFileSync(join(ROOT, 'models3d', 'bbox.json'), 'utf8')).models;

const PY_PROTOCOL = `
import json, sys
sys.path.insert(0, sys.argv[1])
import leancheck
req = json.load(sys.stdin)
sys.stdout.write(leancheck.protocol(req["d"], req["knobs"], req["dni"]))
`;
const PROTOCOL_CASES = [
  { knobs: null, dni: [] },
  { knobs: { ledQty: 7, driveUA: 8000 }, dni: ['C3', 'C14'] },
];

const show = (v) => { const s = JSON.stringify(v); return s === undefined ? 'undefined' : s.length > 90 ? s.slice(0, 90) + '…' : s; };

/** Path and values of the first place where two JSON values differ, or null. */
function firstDiff(want, got, path = '$') {
  if (want === got) return null;
  const obj = (v) => v !== null && typeof v === 'object';
  if (!obj(want) || !obj(got) || Array.isArray(want) !== Array.isArray(got)) {
    return `${path}: pcbnew ${show(want)}, js ${show(got)}`;
  }
  if (Array.isArray(want)) {
    for (let i = 0; i < Math.min(want.length, got.length); i++) {
      const d = firstDiff(want[i], got[i], `${path}[${i}]`);
      if (d) return d;
    }
    return want.length === got.length ? null : `${path}.length: pcbnew ${want.length}, js ${got.length}`;
  }
  const keys = [...new Set([...Object.keys(want), ...Object.keys(got)])];
  for (const k of keys) {
    if (!(k in want) || !(k in got)) return `${path}.${k}: only in ${k in want ? 'pcbnew' : 'js'}`;
    const d = firstDiff(want[k], got[k], `${path}.${k}`);
    if (d) return d;
  }
  return null;
}

/** First differing line of two texts, or null. */
function firstLineDiff(want, got) {
  if (want === got) return null;
  const a = want.split('\n'), b = got.split('\n');
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if (a[i] !== b[i]) return `protocol line ${i + 1}: python ${show(a[i])}, js ${show(b[i])}`;
  }
  return 'protocol texts differ';
}

function check(path) {
  const want = JSON.parse(execFileSync(PYTHON, [join(HERE, 'dump_board_data.py'), path], { ...BIG, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }));
  const warnings = [];
  const got = parseKicadPcb(readFileSync(path, 'utf8'), models, warnings);
  let diff = firstDiff(want, got);
  if (!diff) {
    for (const c of PROTOCOL_CASES) {
      const py = execFileSync(PYTHON, ['-c', PY_PROTOCOL, HERE], { ...BIG, encoding: 'utf8', input: JSON.stringify({ d: want, ...c }), stdio: ['pipe', 'pipe', 'ignore'] });
      diff = firstLineDiff(py, toProtocol(got, c.knobs, c.dni));
      if (diff) break;
    }
  }
  const pads = want.fps.reduce((n, f) => n + f.pads.length, 0);
  return { diff, summary: `${want.n} footprints, ${pads} numbered pads, outline ${want.outline.length} points`, warnings };
}

const boards = readdirSync(join(ROOT, 'pcb')).filter((f) => f.endsWith('.kicad_pcb') && f !== 'sierrathon_grid.kicad_pcb').sort()
  .map((f) => join(ROOT, 'pcb', f)).concat(process.argv.slice(2).map((p) => resolve(p)));

let failed = 0;
for (const path of boards) {
  let r;
  try { r = check(path); } catch (e) { r = { diff: `error: ${e.message.split('\n')[0]}`, summary: '', warnings: [] }; }
  if (r.diff) failed++;
  console.log(`${r.diff ? 'FAIL' : 'PASS'}  ${basename(path)}  ${r.diff ? 'first difference: ' + r.diff : r.summary}`);
  for (const w of [...new Set(r.warnings)].slice(0, 5)) console.log(`      note: ${w}`);
}
console.log(failed ? `${failed} of ${boards.length} boards FAILED` : `all ${boards.length} boards agree with pcbnew (data and protocol text)`);
process.exit(failed ? 1 : 0);
