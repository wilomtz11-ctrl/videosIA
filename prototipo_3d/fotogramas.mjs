// Captura fotogramas sueltos para revisar sin renderizar todo: node fotogramas.mjs 1 5 9 ...
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
const tipos = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.jpg': 'image/jpeg',
  '.png': 'image/png', '.ttf': 'font/ttf', '.bin': 'application/octet-stream', '.wav': 'audio/wav' };
const srv = createServer(async (q, r) => {
  try { const f = join(process.cwd(), decodeURIComponent(q.url.split('?')[0]) === '/' ? 'index.html' : decodeURIComponent(q.url.split('?')[0]));
    r.writeHead(200, { 'content-type': tipos[extname(f)] || 'application/octet-stream' }); r.end(await readFile(f)); }
  catch { r.writeHead(404); r.end(); }
}).listen(8091);
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
p.on('pageerror', e => console.log('[error]', e.message));
await p.goto('http://localhost:8091/');
await p.waitForFunction(() => typeof window.renderAt === 'function', null, { timeout: 120000 });
await p.evaluate(() => document.fonts.ready);
for (const s of process.argv.slice(2).map(Number)) {
  await p.evaluate(t => window.renderAt(t), s);
  await p.screenshot({ path: `../salida/proto_t${s.toFixed(1).padStart(4, '0')}.jpg`, type: 'jpeg', quality: 90, timeout: 120000 });
}
await b.close(); srv.close();
