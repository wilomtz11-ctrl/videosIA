// Vista previa: exporta fotogramas sueltos de un build sin renderizar el video completo.
// Uso: node fotogramas.mjs <carpeta_build> <carpeta_salida> <seg1> <seg2> ...
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { basename, extname, join } from 'node:path';

const [build, salida, ...segs] = process.argv.slice(2);
const TIPOS = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.jpg': 'image/jpeg',
  '.png': 'image/png', '.ttf': 'font/ttf', '.bin': 'application/octet-stream' };
const srv = createServer(async (q, r) => {
  const ruta = decodeURIComponent(q.url.split('?')[0]);
  try {
    const f = join(build, ruta === '/' ? 'index.html' : ruta);
    r.writeHead(200, { 'content-type': TIPOS[extname(f)] || 'application/octet-stream' });
    r.end(await readFile(f));
  } catch { r.writeHead(404); r.end(); }
});
await new Promise(ok => srv.listen(0, ok));
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const { ancho: width, alto: height } = JSON.parse(await readFile(join(build, 'datos', 'escena.json'), 'utf8')).formato;
const page = await browser.newPage({ viewport: { width, height } });
page.on('pageerror', e => console.error('[error en la página]', e.message));
await page.goto(`http://localhost:${srv.address().port}/`);
await page.waitForFunction(() => window.motorListo === true, null, { timeout: 180000 });
await page.evaluate(() => document.fonts.ready);
for (const s of segs.map(Number)) {
  await page.evaluate(t => window.renderAt(t), s);
  await page.screenshot({ path: join(salida, `${basename(build)}_t${s.toFixed(1).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 88, timeout: 180000 });
}
await browser.close(); srv.close();
