// Ask Claude for a new round of build proposals, given Lean's findings on the last round.
// Claude only proposes. The page turns each proposal into a board and the Lean checker rates it.
// Needs ANTHROPIC_API_KEY in the Vercel project settings; without it the page says live proposals are off.
const MODEL = process.env.LEANCHIP_MODEL || 'claude-opus-5-5';

function readBody(req) {
  if (req.body && typeof req.body === 'object' && !Buffer.isBuffer(req.body)) return Promise.resolve(JSON.stringify(req.body));
  if (typeof req.body === 'string') return Promise.resolve(req.body);
  return new Promise((ok, bad) => { const c = []; req.on('data', (d) => c.push(d)); req.on('end', () => ok(Buffer.concat(c).toString('utf8'))); req.on('error', bad); });
}

module.exports = async (req, res) => {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (req.method !== 'POST') { res.statusCode = 405; res.end('{"error":"POST"}'); return; }
  if (!process.env.ANTHROPIC_API_KEY) { res.statusCode = 503; res.end(JSON.stringify({ error: 'no ANTHROPIC_API_KEY set' })); return; }
  try {
    const { menu, feedback, round } = JSON.parse(await readBody(req));
    const prompt = `You are proposing ways to build the Sierrathon RP2040 PCB from its exact BOM. A Lean 4 checker will rate every proposal GREEN, YELLOW or RED; only its verdict counts.
Here is what you may change (use only these exact names and values):
${JSON.stringify(menu)}
Here are Lean's findings on the previous round:
${JSON.stringify(feedback)}
Write round ${round}: three proposals that learn from those findings, each aiming for fewer red and yellow results. Keep the schematic and BOM parts unchanged; you may pick footprints per BOM row, set the listed values, and leave decoupling capacitors off only if you expect the rail to stay above its minimum.
Reply with JSON only: {"proposals":[{"name":"short title","rationale":"one or two sentences citing the findings","lines":{"<row>":"<footprint>"},"knobs":{"<key>":<value>},"dni":["<ref>"]}]}`;
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({ model: MODEL, max_tokens: 2000, messages: [{ role: 'user', content: prompt }] }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error((d.error && d.error.message) || 'Claude API error');
    const text = d.content.map((c) => c.text || '').join('');
    const m = text.match(/\{[\s\S]*\}/);
    const out = JSON.parse(m ? m[0] : text);
    if (!Array.isArray(out.proposals)) throw new Error('no proposals in reply');
    res.statusCode = 200; res.end(JSON.stringify({ proposals: out.proposals.slice(0, 4), model: MODEL }));
  } catch (e) { res.statusCode = 500; res.end(JSON.stringify({ error: String(e.message || e) })); }
};
