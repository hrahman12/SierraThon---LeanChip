#!/usr/bin/env node
// Runs the web tool's named builds through the compiled Lean checker and writes what the page
// needs when the live checker is not reachable (and what the tests assert):
//   site/data/recorded.json   sha256(build text) -> the checker's JSON, for every named build
//   site/data/tests.json      the test cases with expected and actual verdicts
// The build text comes from site/tool_core.js, the same file the browser runs.
//     node leanvsdfm/tools/tool_runs.mjs            (exits 1 if any test fails)
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { defaultState, cloneState, buildText, applyProposal, sha256Hex } from '../../site/tool_core.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const BIN = path.join(root, 'api', '_bin', 'leanchip');
const D = (f) => path.join(root, 'site', 'data', f);
const tool = JSON.parse(fs.readFileSync(D('tool.json'), 'utf8'));
const lean = (text) => {
  const p = spawnSync(BIN, [], { input: text, maxBuffer: 32e6 });
  if (p.status !== 0) throw new Error('checker failed: ' + p.stdout + p.stderr);
  return JSON.parse(p.stdout.toString('utf8'));
};
const recorded = {};
const run = async (state) => {
  const text = buildText(tool, state), h = await sha256Hex(text);
  if (!recorded[h]) recorded[h] = lean(text);
  return recorded[h];
};
const brief = (r) => `${r.overall} (${r.counts.green} green, ${r.counts.yellow} yellow, ${r.counts.red} red)`;

// 1. the package as supplied, then every single change the page offers
const base = defaultState(tool);
const supplied = await run(base);
for (const l of tool.lines) for (let i = 1; i < l.options.length; i++) { const s = cloneState(base); s.lines[l.line] = i; await run(s); }
for (const f of tool.faults) { const s = cloneState(base); s.faults = [f.id]; await run(s); }
for (const k of tool.knobs) for (const o of k.options) { const s = cloneState(base); s.knobs[k.key] = o[0]; await run(s); }
for (const ra of tool.rails) for (const c of ra.caps) { const s = cloneState(base); s.dni = [c.ref]; await run(s); }

// 2. Claude's proposals, round by round
const props = JSON.parse(fs.readFileSync(D('proposals.json'), 'utf8'));
for (const round of props.rounds) for (const p of round.proposals) {
  const r = await run(applyProposal(tool, p));
  if (process.argv.includes('--show')) {
    console.log(`\nround ${round.round} · ${p.name}: ${brief(r)}`);
    for (const row of r.rows) if (row.color !== 'GREEN') console.log(`   ${row.color.padEnd(6)} ${row.check}: ${row.detail.slice(0, 160)}`);
  }
}

// 3. test cases: expected verdicts are written down before the checker runs
const tests = JSON.parse(fs.readFileSync(path.join(root, 'leanvsdfm', 'tools', 'tool_tests.json'), 'utf8'));
let failed = 0;
const out = [];
for (const t of tests.tests) {
  const r = await run(applyProposal(tool, t.build));
  const comp = Object.fromEntries(r.components.map((c) => [c.ref, c.color]));
  const checks = [{ what: 'overall', expected: t.expect.overall, actual: r.overall }];
  for (const [ref, col] of Object.entries(t.expect.components || {})) checks.push({ what: ref, expected: col, actual: comp[ref] });
  for (const [frag, col] of Object.entries(t.expect.rows || {})) {
    const row = r.rows.find((x) => x.check.includes(frag));
    checks.push({ what: frag, expected: col, actual: row ? row.color : 'no such row' });
  }
  const pass = checks.every((c) => c.expected === c.actual);
  if (!pass) { failed++; console.log('FAIL', t.name, JSON.stringify(checks.filter((c) => c.expected !== c.actual))); }
  out.push({ name: t.name, why: t.why, build: t.build, checks, pass, overall: r.overall, counts: r.counts });
}
fs.writeFileSync(D('recorded.json'), JSON.stringify(recorded));
fs.writeFileSync(D('tests.json'), JSON.stringify({ about: 'Written by leanvsdfm/tools/tool_runs.mjs from the compiled Lean checker.', supplied: brief(supplied), passed: out.length - failed, total: out.length, tests: out }, null, 1));
console.log(`supplied package: ${brief(supplied)}`);
console.log(`${Object.keys(recorded).length} builds recorded; tests ${out.length - failed}/${out.length} passed`);
process.exit(failed ? 1 : 0);
