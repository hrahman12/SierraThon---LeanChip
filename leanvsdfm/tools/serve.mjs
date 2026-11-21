#!/usr/bin/env node
// Run the website locally with the real Lean checker behind it:
//     node leanvsdfm/tools/serve.mjs [port]        then open http://localhost:8080
// Serves site/ and routes /api/* to the same handlers Vercel runs.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const require = createRequire(import.meta.url);
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.css': 'text/css',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.glb': 'model/gltf-binary', '.woff2': 'font/woff2', '.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.webp': 'image/webp',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.kicad_pcb': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8' };
const port = Number(process.argv[2] || 8080);

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname.startsWith('/api/')) {
    const name = url.pathname.slice(5).replace(/[^a-z0-9_-]/gi, '');
    const file = path.join(root, 'api', name + '.js');
    if (!fs.existsSync(file)) { res.writeHead(404, { 'Content-Type': 'application/json' }); res.end('{"error":"no such endpoint"}'); return; }
    try { await require(file)(req, res); } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: String(e) })); }
    return;
  }
  let p = path.normalize(path.join(root, 'site', decodeURIComponent(url.pathname)));
  if (!p.startsWith(path.join(root, 'site'))) { res.writeHead(403); res.end(); return; }
  if (fs.existsSync(p) && fs.statSync(p).isDirectory()) p = path.join(p, 'index.html');
  if (!fs.existsSync(p) && fs.existsSync(p + '.html')) p += '.html';
  if (!fs.existsSync(p)) { res.writeHead(404); res.end('not found'); return; }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(p)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
  fs.createReadStream(p).pipe(res);
}).listen(port, () => console.log(`LeanChip on http://localhost:${port}  (Lean checker: api/_bin/leanchip)`));
