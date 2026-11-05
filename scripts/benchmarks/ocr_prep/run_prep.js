const fs = require('fs'), path = require('path');
const [,, modPath, dataDir, outDir, optsJson] = process.argv;
const P = require(modPath); const opts = optsJson ? JSON.parse(optsJson) : undefined;
fs.mkdirSync(outDir, { recursive: true });
const meta = JSON.parse(fs.readFileSync(path.join(dataDir, 'meta.json')));
function pgm(f, a, w, h) { fs.writeFileSync(f, Buffer.concat([Buffer.from(`P5\n${w} ${h}\n255\n`), Buffer.from(a)])); }
let tot = 0;
for (const m of meta) {
  const px = new Uint8ClampedArray(fs.readFileSync(path.join(dataDir, m.id + '.rgba')));
  const t = process.hrtime.bigint();
  const r = P.process(px, m.w, m.h, opts);
  tot += Number(process.hrtime.bigint() - t) / 1e6;
  pgm(path.join(outDir, m.id + '.gray.pgm'), r.st, m.w, m.h);
  let bin = r.bin; if (!bin) { bin = new Uint8ClampedArray(r.st.length); for (let i = 0; i < bin.length; i++) bin[i] = r.st[i] > r.thr ? 255 : 0; }
  pgm(path.join(outDir, m.id + '.bin.pgm'), bin, m.w, m.h);
  const inv = new Uint8ClampedArray(r.st.length); for (let i = 0; i < inv.length; i++) inv[i] = 255 - r.st[i];
  pgm(path.join(outDir, m.id + '.inv.pgm'), inv, m.w, m.h);
  fs.writeFileSync(path.join(outDir, m.id + '.q.json'), JSON.stringify({ sharp: r.sharp, q: r.q || null }));
}
console.log('avg ms/image', (tot / meta.length).toFixed(1));
