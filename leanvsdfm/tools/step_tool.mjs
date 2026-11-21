// STEP utilities built on OpenCascade (occt-import-js).
//   node step_tool.mjs bbox <a.step> [b.step ...]      -> JSON {file: {min:[x,y,z], max:[x,y,z]}} in mm
//   node step_tool.mjs glb  <board.step> <out.glb> <out.json>
//        -> binary glTF (y-up, mm) + JSON list of top-level parts with name and bbox (z-up, mm)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const occt = await require('occt-import-js')();

function read(file) {
  const r = occt.ReadStepFile(new Uint8Array(fs.readFileSync(file)), { linearUnit: 'millimeter', linearDeflectionType: 'absolute_value', linearDeflection: 0.02, angularDeflection: 0.35 });
  if (!r.success) throw new Error('OCCT could not read ' + file);
  return r;
}
function bboxOf(meshes) {
  const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
  for (const m of meshes) {
    const p = m.attributes.position.array;
    for (let i = 0; i < p.length; i += 3) for (let k = 0; k < 3; k++) { if (p[i + k] < mn[k]) mn[k] = p[i + k]; if (p[i + k] > mx[k]) mx[k] = p[i + k]; }
  }
  return { min: mn.map(v => +v.toFixed(4)), max: mx.map(v => +v.toFixed(4)) };
}
function collect(node, r, out) { for (const i of node.meshes) out.push(r.meshes[i]); for (const c of node.children) collect(c, r, out); return out; }

const [cmd, ...args] = process.argv.slice(2);
if (cmd === 'bbox') {
  const out = {};
  for (const f of args) out[path.basename(f)] = bboxOf(read(f).meshes);
  console.log(JSON.stringify(out, null, 1));
} else if (cmd === 'glb') {
  const [src, dst, meta] = args;
  const r = read(src);
  // ---- part list (top-level children of the assembly) ----
  let top = r.root; while (top.children.length === 1 && top.meshes.length === 0) top = top.children[0];
  const parts = top.children.map(c => ({ name: c.name, ...bboxOf(collect(c, r, [])) }));
  // ---- GLB ----
  const bufs = []; let off = 0;
  const views = [], accessors = [], materials = [], matIndex = new Map(), gmeshes = [], nodes = [];
  const push = (typed, target) => { const b = Buffer.from(typed.buffer, typed.byteOffset, typed.byteLength); const pad = (4 - (b.length % 4)) % 4;
    views.push({ buffer: 0, byteOffset: off, byteLength: b.length, target }); bufs.push(b, Buffer.alloc(pad)); off += b.length + pad; return views.length - 1; };
  const mat = (c) => { const key = c.map(v => v.toFixed(3)).join(','); if (!matIndex.has(key)) { matIndex.set(key, materials.length);
    materials.push({ pbrMetallicRoughness: { baseColorFactor: [c[0], c[1], c[2], 1], metallicFactor: 0.15, roughnessFactor: 0.6 } }); } return matIndex.get(key); };
  for (const m of r.meshes) {
    const pos = new Float32Array(m.attributes.position.array), idx = new Uint32Array(m.index.array);
    if (!pos.length || !idx.length) { gmeshes.push(null); continue; }
    const b = bboxOf([m]);
    const pv = push(pos, 34962); accessors.push({ bufferView: pv, componentType: 5126, count: pos.length / 3, type: 'VEC3', min: b.min, max: b.max }); const pa = accessors.length - 1;
    let na;
    if (m.attributes.normal) { const nv = push(new Float32Array(m.attributes.normal.array), 34962); accessors.push({ bufferView: nv, componentType: 5126, count: pos.length / 3, type: 'VEC3' }); na = accessors.length - 1; }
    const base = m.color || [0.6, 0.6, 0.6];
    const groups = new Map(); const tri = idx.length / 3; const faceColor = new Array(tri).fill(null);
    for (const f of (m.brep_faces || [])) if (f.color) for (let t = f.first; t <= f.last; t++) faceColor[t] = f.color;
    for (let t = 0; t < tri; t++) { const c = faceColor[t] || base; const k = mat(c); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(idx[3 * t], idx[3 * t + 1], idx[3 * t + 2]); }
    const prims = [];
    for (const [k, arr] of groups) { const iv = push(new Uint32Array(arr), 34963); accessors.push({ bufferView: iv, componentType: 5125, count: arr.length, type: 'SCALAR' });
      const attributes = { POSITION: pa }; if (na !== undefined) attributes.NORMAL = na; prims.push({ attributes, indices: accessors.length - 1, material: k }); }
    gmeshes.push({ name: m.name, primitives: prims });
  }
  const meshMap = []; const outMeshes = []; gmeshes.forEach((g, i) => { if (g) { meshMap[i] = outMeshes.length; outMeshes.push(g); } });
  const addNode = (n) => { const me = { name: n.name }; const kids = [];
    for (const i of n.meshes) if (meshMap[i] !== undefined) { nodes.push({ name: r.meshes[i].name, mesh: meshMap[i] }); kids.push(nodes.length - 1); }
    for (const c of n.children) kids.push(addNode(c)); if (kids.length) me.children = kids; nodes.push(me); return nodes.length - 1; };
  const rootIdx = addNode(r.root);
  nodes.push({ name: 'y_up', rotation: [-0.70710678, 0, 0, 0.70710678], children: [rootIdx] });
  const json = { asset: { version: '2.0', generator: 'leanvsdfm step_tool (OpenCascade)' }, scene: 0, scenes: [{ nodes: [nodes.length - 1] }], nodes, meshes: outMeshes, materials, accessors, bufferViews: views, buffers: [{ byteLength: off }] };
  let jb = Buffer.from(JSON.stringify(json)); jb = Buffer.concat([jb, Buffer.alloc((4 - (jb.length % 4)) % 4, 0x20)]);
  const bin = Buffer.concat(bufs); const head = Buffer.alloc(12); head.writeUInt32LE(0x46546C67, 0); head.writeUInt32LE(2, 4); head.writeUInt32LE(12 + 8 + jb.length + 8 + bin.length, 8);
  const jh = Buffer.alloc(8); jh.writeUInt32LE(jb.length, 0); jh.writeUInt32LE(0x4E4F534A, 4); const bh = Buffer.alloc(8); bh.writeUInt32LE(bin.length, 0); bh.writeUInt32LE(0x004E4942, 4);
  fs.writeFileSync(dst, Buffer.concat([head, jh, jb, bh, bin]));
  fs.writeFileSync(meta, JSON.stringify({ source: path.basename(src), parts }, null, 1));
  console.log(`wrote ${dst} (${(fs.statSync(dst).size / 1e6).toFixed(2)} MB), ${outMeshes.length} meshes, ${materials.length} materials, ${parts.length} top-level parts`);
} else { console.error('usage: step_tool.mjs bbox <files> | glb <board.step> <out.glb> <out.json>'); process.exit(2); }
