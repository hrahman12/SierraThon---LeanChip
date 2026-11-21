// LeanChip tool core. Runs in the browser and in Node (tests use the very same file).
// It holds NO verdict logic: it only turns a choice of options into the text the Lean checker
// reads. Every colour on the page comes back from the `leanchip` binary (compiled Lean).

export function defaultState(tool) {
  const lines = {};
  for (const l of tool.lines) lines[l.line] = 0;
  return { lines, faults: [], knobs: { ...tool.defaults }, dni: [] };
}

export function cloneState(s) {
  return { lines: { ...s.lines }, faults: [...s.faults], knobs: { ...s.knobs }, dni: [...s.dni] };
}

/** The exact input for the checker: knobs, unpopulated parts, outline, footprints, parts. */
export function buildText(tool, state) {
  const out = [];
  for (const k of tool.knobs) {
    const v = state.knobs[k.key];
    if (k.sets) String(v).split('/').forEach((x, i) => out.push(`K\t${k.sets[i]}\t${x}`));
    else out.push(`K\t${k.key}\t${v}`);
  }
  for (const r of tool.order) if (state.dni.includes(r)) out.push(`D\t${r}`);
  out.push(`B\tthickness\t${tool.thickness_nm}`);
  for (const [x, y] of tool.outline) out.push(`O\t${x}\t${y}`);
  const pick = {};
  for (const r of Object.keys(tool.fixed)) pick[r] = tool.fixed[r];
  for (const l of tool.lines) {
    const o = l.options[state.lines[l.line] ?? 0] ?? l.options[0];
    for (const r of l.refs) pick[r] = o.per_ref[r];
  }
  for (const f of tool.faults) if (state.faults.includes(f.id)) for (const r of Object.keys(f.per_ref)) pick[r] = f.per_ref[r];
  for (const r of tool.order) out.push(...pick[r].f);
  for (const r of tool.order) out.push(pick[r].t);
  return out.join('\n') + '\n';
}

/** What differs from the package as supplied (for labels; not used for verdicts). */
export function changes(tool, state) {
  const c = [];
  for (const l of tool.lines) if ((state.lines[l.line] ?? 0) !== 0) c.push(`row ${l.line} (${l.refs.join(', ')}): ${l.options[state.lines[l.line]].id}`);
  for (const f of tool.faults) if (state.faults.includes(f.id)) c.push(f.label);
  for (const k of tool.knobs) if (String(state.knobs[k.key]) !== String(tool.defaults[k.key])) c.push(`${k.label}: ${(k.options.find((o) => String(o[0]) === String(state.knobs[k.key])) || [0, state.knobs[k.key]])[1]}`);
  if (state.dni.length) c.push(`not fitted: ${state.dni.join(', ')}`);
  return c;
}

/** A proposal (from Claude or anyone) is a list of changes to the supplied design. */
export function applyProposal(tool, p) {
  const s = defaultState(tool);
  for (const [ln, id] of Object.entries(p.lines || {})) {
    const l = tool.lines.find((x) => String(x.line) === String(ln));
    if (!l) throw new Error(`no BOM row ${ln} to change`);
    const i = l.options.findIndex((o) => o.id === id || o.id.startsWith(id + ' ('));
    if (i < 0) throw new Error(`BOM row ${ln}: unknown footprint ${id}`);
    s.lines[l.line] = i;
  }
  for (const [k, v] of Object.entries(p.knobs || {})) {
    const kn = tool.knobs.find((x) => x.key === k);
    if (!kn) throw new Error(`unknown setting ${k}`);
    if (!kn.options.some((o) => String(o[0]) === String(v))) throw new Error(`${k}: ${v} is not one of the allowed values`);
    s.knobs[k] = kn.options.find((o) => String(o[0]) === String(v))[0];
  }
  for (const r of p.dni || []) {
    if (!tool.rails.some((ra) => ra.caps.some((c) => c.ref === r))) throw new Error(`${r} is not a decoupling capacitor`);
    if (!s.dni.includes(r)) s.dni.push(r);
  }
  for (const f of p.faults || []) if (tool.faults.some((x) => x.id === f)) s.faults.push(f);
  return s;
}

export async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const subtle = globalThis.crypto && globalThis.crypto.subtle;
  if (!subtle) throw new Error('no SubtleCrypto');
  const h = await subtle.digest('SHA-256', data);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
