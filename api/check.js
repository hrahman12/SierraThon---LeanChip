// POST a build (the text format in leanvsdfm/Main.lean) -> the Lean checker's report as JSON.
// This function only passes bytes to the compiled Lean binary and returns what it prints.
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '_bin', 'leanchip');
let bin = null;
function checker() {
  if (bin) return bin;
  try {                       // make sure it is executable wherever the platform unpacked it
    fs.accessSync(SRC, fs.constants.X_OK);
    bin = SRC;
  } catch (e) {
    const dst = path.join(require('os').tmpdir(), 'leanchip');
    fs.copyFileSync(SRC, dst);
    fs.chmodSync(dst, 0o755);
    bin = dst;
  }
  return bin;
}

function readBody(req) {
  if (typeof req.body === 'string') return Promise.resolve(req.body);
  if (Buffer.isBuffer(req.body)) return Promise.resolve(req.body.toString('utf8'));
  return new Promise((resolve, reject) => {
    let n = 0; const chunks = [];
    req.on('data', (c) => { n += c.length; if (n > 2e6) { reject(new Error('too large')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

module.exports = async (req, res) => {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'GET') { res.statusCode = 200; res.end(JSON.stringify({ ok: true, checker: 'Lean 4, compiled from LeanVsDFM/Check.lean' })); return; }
  if (req.method !== 'POST') { res.statusCode = 405; res.end(JSON.stringify({ error: 'POST a build as text' })); return; }
  try {
    const body = await readBody(req);
    if (!body || body.length > 2e6) { res.statusCode = 400; res.end(JSON.stringify({ error: 'empty or too large' })); return; }
    const t0 = Date.now();
    const p = spawnSync(checker(), [], { input: body, maxBuffer: 16e6, timeout: 9000 });
    const out = (p.stdout || '').toString('utf8').trim();
    if (!out) { res.statusCode = 500; res.end(JSON.stringify({ error: 'checker gave no output', detail: String(p.error || (p.stderr || '').toString().slice(0, 300)) })); return; }
    res.statusCode = p.status === 0 ? 200 : 400;
    res.setHeader('X-Lean-ms', String(Date.now() - t0));
    res.end(out);
  } catch (e) {
    res.statusCode = 500; res.end(JSON.stringify({ error: String(e.message || e) }));
  }
};
