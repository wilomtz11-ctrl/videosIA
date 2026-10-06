// Motor 3D genérico: dibuja cualquier episodio a partir de datos/escena.json.
// Determinista: cada fotograma depende solo del tiempo t (sin relojes ni azar).
// HyperFrames llama a renderAt(t) mediante el evento 'hf-seek'.
import * as THREE from './lib/three.module.js';
window.THREE = THREE;   // HyperFrames espera a que terminen las cargas del DefaultLoadingManager

// El evento de HyperFrames se registra ANTES de cargar nada: si un fotograma se pide mientras el motor
// aún carga (pasa en 4K o en máquinas lentas), la captura espera con waitUntil en vez de salir vacía.
let avisarListo;
const listo = new Promise(ok => { avisarListo = ok; });
window.addEventListener('hf-seek', e => {
  const t = e.detail.time;
  e.detail.waitUntil(listo.then(render => render(t)));
});

const R_TIERRA = 6371000;
const deg = Math.PI / 180;
const clamp01 = x => Math.max(0, Math.min(1, x));
const suave = x => { x = clamp01(x); return x * x * x * (x * (6 * x - 15) + 10); };
const rampa = (t, a, d) => suave((t - a) / d);
const lerp = (a, b, k) => a + (b - a) * k;
const hex = c => new THREE.Color(c);
const $ = id => document.getElementById(id);

// ---------- datos ----------
const fl = () => new THREE.FileLoader();
const E = await fl().setResponseType('json').loadAsync('./datos/escena.json');
const W = E.formato.ancho, H = E.formato.alto;
const tl = new THREE.TextureLoader();
const cargarTex = (u, srgb = false) => tl.loadAsync(u).then(t => { if (srgb) t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; });
const [texMarble, texRelieve, texF0, texF1, alturasBuf, ...mapasCarg] = await Promise.all([
  cargarTex('./datos/blue-marble.jpg', true), cargarTex('./datos/textura.jpg', true),
  cargarTex('./datos/formas_0.png'), cargarTex('./datos/formas_1.png'),
  fl().setResponseType('arraybuffer').loadAsync('./datos/relieve.bin'),
  ...E.mapas.flatMap(m => [cargarTex(`./datos/mapa_${m.id}.png`, true), fl().setResponseType('json').loadAsync(`./datos/lineas_${m.id}.json`)]),
]);
const MAPAS = {};
E.mapas.forEach((m, i) => { MAPAS[m.id] = { tex: mapasCarg[2 * i], lineas: mapasCarg[2 * i + 1] }; });

const [LON0, LAT0, LON1, LAT1] = E.region, N = E.rejilla, EXAG = E.exageracion;
const alturas = new Float32Array(alturasBuf);
function alturaEn(lon, lat) {   // metros (bilineal); 0 fuera de la región
  if (lon < LON0 || lon > LON1 || lat < LAT0 || lat > LAT1) return 0;
  const x = (lon - LON0) / (LON1 - LON0) * (N - 1), y = (LAT1 - lat) / (LAT1 - LAT0) * (N - 1);
  const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(N - 1, x0 + 1), y1 = Math.min(N - 1, y0 + 1);
  const fx = x - x0, fy = y - y0;
  return lerp(lerp(alturas[y0 * N + x0], alturas[y0 * N + x1], fx), lerp(alturas[y1 * N + x0], alturas[y1 * N + x1], fx), fy);
}
function v3(lon, lat, r = 1) {
  const f = lat * deg, l = lon * deg;
  return new THREE.Vector3(r * Math.cos(f) * Math.sin(l), r * Math.sin(f), r * Math.cos(f) * Math.cos(l));
}
const radioSuelo = (lon, lat) => 1 + alturaEn(lon, lat) * EXAG / R_TIERRA;

// ---------- escena ----------
const renderer = new THREE.WebGLRenderer({ antialias: E.antialias !== false, preserveDrawingBuffer: true });
renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.setSize(W, H);
renderer.outputColorSpace = THREE.SRGBColorSpace;
$('escena').appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, W / H, 0.001, 100);

const tierra = new THREE.Mesh(new THREE.SphereGeometry(1, 192, 96),
  new THREE.MeshStandardMaterial({ map: texMarble, roughness: 0.95, metalness: 0 }));
tierra.rotation.y = -Math.PI / 2;
scene.add(tierra);
scene.add(new THREE.AmbientLight(0xffffff, 0.8));
const sol = new THREE.DirectionalLight(0xffffff, 1.9);
scene.add(sol);

const atmosfera = new THREE.Mesh(new THREE.SphereGeometry(1.06, 96, 48), new THREE.ShaderMaterial({
  side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
  uniforms: { uOpac: { value: 1 } },
  vertexShader: `varying vec3 n; void main(){ n = normalize(normalMatrix*normal); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
  fragmentShader: `uniform float uOpac; varying vec3 n; void main(){ float i = pow(0.72 - dot(n, vec3(0,0,1.)), 3.0); gl_FragColor = vec4(0.35,0.62,1.0,1.0)*i*1.7*uOpac; }`,
}));
scene.add(atmosfera);

{ // estrellas con semilla fija
  let s = 11; const azar = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const p = [];
  for (let i = 0; i < 5000; i++) { const v = new THREE.Vector3(azar() - .5, azar() - .5, azar() - .5).normalize().multiplyScalar(40); p.push(v.x, v.y, v.z); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0xffffff, size: 0.05 })));
}

// ---------- relieve de la región (desplazado en la GPU) ----------
const transparente = new THREE.DataTexture(new Uint8Array([0, 0, 0, 0]), 1, 1); transparente.needsUpdate = true;
const NF = 8;
const uRel = {
  uTex: { value: texRelieve }, uF0: { value: texF0 }, uF1: { value: texF1 },
  uMapaA: { value: transparente }, uMapaB: { value: transparente }, uMezclaMapa: { value: 0 }, uOpacMapa: { value: 1 },
  uExag: { value: EXAG }, uT: { value: 0 },
  uBrillo: { value: new Array(NF).fill(0) }, uColorBrillo: { value: Array.from({ length: NF }, () => new THREE.Vector3()) },
  uPintura: { value: new Array(NF).fill(0) }, uColorPintura: { value: Array.from({ length: NF }, () => new THREE.Vector3()) },
  uAlza: { value: new Array(NF).fill(0) },
};
{
  const pos = new Float32Array(N * N * 3), uv = new Float32Array(N * N * 2);
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const k = j * N + i, u = i / (N - 1), v = j / (N - 1), p = v3(lerp(LON0, LON1, u), lerp(LAT1, LAT0, v));
    pos.set([p.x, p.y, p.z], 3 * k); uv.set([u, 1 - v], 2 * k);
  }
  const idx = new Uint32Array((N - 1) * (N - 1) * 6);
  let q = 0;
  for (let j = 0; j < N - 1; j++) for (let i = 0; i < N - 1; i++) { const a = j * N + i; idx.set([a, a + N, a + 1, a + 1, a + N, a + N + 1], q); q += 6; }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  g.setAttribute('h', new THREE.BufferAttribute(alturas, 1));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  // las 8 máscaras se leen UNA vez por píxel (2 lecturas de textura) y se indexan después
  const mascaras = `
    void leerMascaras(vec2 uv, out float m[${NF}]){ vec4 a = texture2D(uF0, uv), b = texture2D(uF1, uv);
      m[0]=a.r; m[1]=a.g; m[2]=a.b; m[3]=a.a; m[4]=b.r; m[5]=b.g; m[6]=b.b; m[7]=b.a; }`;
  scene.add(new THREE.Mesh(g, new THREE.ShaderMaterial({
    uniforms: uRel, transparent: true,
    vertexShader: `
      attribute float h; uniform float uExag; uniform float uAlza[${NF}]; uniform sampler2D uF0, uF1;
      varying vec2 vUv; ${mascaras}
      void main(){
        vUv = uv; float alza = 0.0; float m[${NF}]; leerMascaras(uv, m);
        for (int i = 0; i < ${NF}; i++) alza += uAlza[i] * m[i];
        vec3 p = normalize(position) * (1.0004 + h * uExag / ${R_TIERRA}.0 + alza);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }`,
    fragmentShader: `
      uniform sampler2D uTex, uF0, uF1, uMapaA, uMapaB; uniform float uMezclaMapa, uOpacMapa, uT;
      uniform float uBrillo[${NF}], uPintura[${NF}]; uniform vec3 uColorBrillo[${NF}], uColorPintura[${NF}];
      varying vec2 vUv; ${mascaras}
      void main(){
        vec3 c = texture2D(uTex, vUv).rgb;
        vec4 ma = texture2D(uMapaA, vUv), mb = texture2D(uMapaB, vUv);
        vec4 m = mix(ma, mb, uMezclaMapa);
        c = mix(c, m.rgb, m.a * uOpacMapa);
        float pulso = 0.6 + 0.4 * sin(uT * 5.0);
        float mk[${NF}]; leerMascaras(vUv, mk);
        for (int i = 0; i < ${NF}; i++) {
          float k = mk[i];
          c = mix(c, uColorPintura[i], uPintura[i] * k * 0.62);
          float borde = smoothstep(0.15, 0.5, k) * (1.0 - smoothstep(0.5, 0.85, k));
          c += uColorBrillo[i] * uBrillo[i] * (k * 0.35 * pulso + borde * 1.3);
        }
        float e = min(min(vUv.x, 1.0 - vUv.x), min(vUv.y, 1.0 - vUv.y));
        gl_FragColor = vec4(c, smoothstep(0.0, 0.12, e));
        #include <colorspace_fragment>
      }`,
  })));
}

// ---------- fronteras por mapa (pegadas al relieve) ----------
const LINEAS = {};
for (const [id, m] of Object.entries(MAPAS)) {
  const s = m.lineas, pos = new Float32Array(s.length / 2 * 3);
  for (let i = 0; i < s.length; i += 2) { const p = v3(s[i], s[i + 1], radioSuelo(s[i], s[i + 1]) + 0.0009); pos.set([p.x, p.y, p.z], i / 2 * 3); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const obj = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, depthWrite: false }));
  scene.add(obj); LINEAS[id] = obj;
}

// ---------- flechas: arcos 3D que crecen ----------
const FLECHAS = E.flechas.map(f => {
  const a = v3(f.de[0], f.de[1]), b = v3(f.a[0], f.a[1]);
  const pts = [];
  for (let i = 0; i <= 64; i++) {
    const k = i / 64, p = a.clone().lerp(b, k).normalize();
    const lon = Math.atan2(p.x, p.z) / deg, lat = Math.asin(p.y) / deg;
    pts.push(p.multiplyScalar(radioSuelo(lon, lat) + 0.004 + 0.06 * a.distanceTo(b) * Math.sin(Math.PI * k)));
  }
  const tubo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 128, 0.0035, 8, false);
  const mat = new THREE.MeshBasicMaterial({ color: hex(f.color), transparent: true, depthTest: false });
  const malla = new THREE.Mesh(tubo, mat); malla.renderOrder = 5; scene.add(malla);
  return { f, malla, total: tubo.index.count };
});

// ---------- cámara ----------
function ponerCamara(lon, lat, alt, incl, rumbo) {
  const obj = v3(lon, lat, radioSuelo(lon, lat));
  const arriba = obj.clone().normalize();
  const l = lon * deg, f = lat * deg;
  const este = new THREE.Vector3(Math.cos(l), 0, -Math.sin(l));
  const norte = new THREE.Vector3(-Math.sin(f) * Math.sin(l), Math.cos(f), -Math.sin(f) * Math.cos(l));
  const dir = norte.clone().multiplyScalar(Math.cos(rumbo * deg)).addScaledVector(este, Math.sin(rumbo * deg));
  const p = incl * deg;
  camera.position.copy(obj).addScaledVector(arriba, alt * Math.cos(p)).addScaledVector(dir, -alt * Math.sin(p));
  camera.up.copy(arriba.clone().multiplyScalar(Math.sin(p)).addScaledVector(dir, Math.cos(p)).normalize());
  camera.near = Math.max(0.0005, alt * 0.05); camera.far = alt + 6; camera.updateProjectionMatrix();
  camera.lookAt(obj);
  sol.position.copy(camera.position).addScaledVector(arriba, 2).addScaledVector(este, -1.5);
}
function camaraEn(t) {
  const K = E.camara;
  let i = 0; while (i < K.length - 2 && t > K[i + 1][0]) i++;
  const a = K[i], b = K[i + 1], k = b[0] > a[0] ? suave((t - a[0]) / (b[0] - a[0])) : 1;
  let dl = b[1] - a[1]; if (dl > 180) dl -= 360; if (dl < -180) dl += 360;
  return [a[1] + dl * k, lerp(a[2], b[2], k), Math.exp(lerp(Math.log(a[3]), Math.log(b[3]), k)), lerp(a[4], b[4], k), lerp(a[5], b[5], k)];
}

// ---------- capa HTML: etiquetas, anillos, titulares, año, subtítulos ----------
const capa = $('capa');
const crear = (clase, html, estilo = '') => { const d = document.createElement('div'); d.className = clase; d.innerHTML = html; d.style.cssText = estilo; capa.appendChild(d); return d; };
const ETQ = E.etiquetas.map(e => ({ e, el: crear(`etq ${e.estilo}`, e.texto, `font-size:${e.tam}px`) }));
const ANI = E.anillos.map(a => ({ a, el: crear('anillo', '', `border-color:${a.color};color:${a.color}`) }));
const SUB = crear('subs', '');
function proyectar(lon, lat) {
  const p = v3(lon, lat, radioSuelo(lon, lat) + 0.002);
  const visible = p.clone().normalize().dot(camera.position.clone().sub(p)) > 0;
  const s = p.project(camera);
  return { x: (s.x + 1) / 2 * W, y: (1 - s.y) / 2 * H, visible: visible && s.z < 1 };
}
const env = (t, t0, t1, ent = 0.35, sal = 0.3) => (t0 <= 0.001 ? 1 : rampa(t, t0, ent)) * (1 - rampa(t, t1 - sal, sal));
const ZONA_SUP = H * 0.31, ZONA_INF = H * 0.93;
const zona = (x, y) => clamp01((y - ZONA_SUP) / 80) * clamp01((ZONA_INF - y) / 60) * clamp01((x - 70) / 60) * clamp01((W - 70 - x) / 60);

function anioEn(t) {
  const A = E.anios; if (!A.length) return '';
  let i = -1; while (i + 1 < A.length && A[i + 1][0] <= t) i++;
  if (i < 0) return String(A[0][1]);
  const [ti, v] = A[i], prev = i > 0 ? A[i - 1][1] : null;
  if (typeof v === 'number' && typeof prev === 'number' && t < ti + 0.9) return String(Math.round(lerp(prev, v, suave((t - ti) / 0.9))));
  return String(v);
}

function renderAt(t) {
  // cámara
  const [lo, la, alt, inc, rum] = camaraEn(t);
  ponerCamara(lo, la, alt, inc, rum);
  atmosfera.material.uniforms.uOpac.value = clamp01((alt - 0.25) / 0.6);
  // mapa político con fundido
  const P = E.mapas_pistas; let j = 0; while (j + 1 < P.length && P[j + 1][0] <= t) j++;
  const actual = P[j][1], anterior = j > 0 ? P[j - 1][1] : actual, k = j > 0 ? rampa(t, P[j][0], E.transicion_mapa) : 1;
  uRel.uMapaA.value = MAPAS[anterior]?.tex || transparente; uRel.uMapaB.value = MAPAS[actual]?.tex || transparente;
  uRel.uMezclaMapa.value = k;
  uRel.uOpacMapa.value = 0.3 + 0.7 * suave((alt - 0.2) / 0.6);   // de cerca, el relieve manda
  for (const [id, l] of Object.entries(LINEAS)) l.material.opacity = 0.75 * (id === actual ? k : id === anterior ? 1 - k : 0);
  // formas: brillo, pintura, alza
  uRel.uT.value = t;
  uRel.uBrillo.value.fill(0); uRel.uPintura.value.fill(0); uRel.uAlza.value.fill(0);
  for (const ev of E.formas_eventos) {
    const i = E.formas[ev.forma][0] * 4 + E.formas[ev.forma][1];
    if (ev.tipo === 'resaltar' && t >= ev.t0 - 0.5 && t <= ev.t1) {
      const b = env(t, ev.t0, ev.t1, 0.5, 0.4);
      if (b > uRel.uBrillo.value[i]) { uRel.uBrillo.value[i] = b; uRel.uColorBrillo.value[i].set(...hex(ev.color).toArray()); }
    } else if (ev.tipo === 'pintar' && t >= ev.t) {
      uRel.uPintura.value[i] = rampa(t, ev.t, ev.dur); uRel.uColorPintura.value[i].set(...hex(ev.color).toArray());
      uRel.uAlza.value[i] = 0.0015 * Math.sin(Math.PI * clamp01((t - ev.t) / ev.dur));
    } else if (ev.tipo === 'despintar' && t >= ev.t) {
      uRel.uPintura.value[i] *= 1 - rampa(t, ev.t, ev.dur);
    }
  }
  // flechas
  for (const { f, malla, total } of FLECHAS) {
    const p = rampa(t, f.t0, f.dur);
    malla.visible = t >= f.t0 && t <= f.t1;
    malla.geometry.setDrawRange(0, Math.floor(total * p / 6) * 6);
    malla.material.opacity = 1 - rampa(t, f.t1 - 0.3, 0.3);
  }
  renderer.render(scene, camera);

  // HTML
  for (const { e, el } of ETQ) {
    const a = t >= e.t0 - 0.1 && t <= e.t1 ? env(t, e.t0, e.t1) : 0;
    if (a <= 0) { el.style.opacity = 0; continue; }
    const s = proyectar(e.lon, e.lat);
    el.style.left = s.x + 'px'; el.style.top = s.y + 'px';
    el.style.opacity = s.visible ? a * zona(s.x, s.y) : 0;
  }
  for (const { a, el } of ANI) {
    const v = t >= a.t0 && t <= a.t1 ? env(t, a.t0, a.t1) : 0;
    if (v <= 0) { el.style.opacity = 0; continue; }
    const s = proyectar(a.lon, a.lat), r = 40 * (1 + 0.15 * Math.sin((t - a.t0) * 6));
    Object.assign(el.style, { left: s.x + 'px', top: s.y + 'px', width: 2 * r + 'px', height: 2 * r + 'px', opacity: s.visible ? v * zona(s.x, s.y) : 0 });
  }
  const an = $('anio'); an.textContent = anioEn(t);
  const tit = E.titulares.find(x => t >= x.t0 && t < x.t1), ti = $('titular');
  if (tit) {
    const kk = tit.t0 <= 0.001 ? 1 : clamp01((t - tit.t0) / 0.35);
    ti.textContent = tit.texto; ti.className = tit.estilo;
    ti.style.opacity = env(t, tit.t0, tit.t1, 0.2, 0.25);
    ti.style.transform = `translateX(-50%) scale(${(0.82 + 0.18 * suave(kk)) * (1 + 0.1 * Math.sin(Math.PI * kk) * (1 - kk))})`;
  } else ti.style.opacity = 0;
  const g = E.subtitulos.find(x => t >= x.t0 && t < x.t1);
  if (g) {
    SUB.innerHTML = g.palabras.map(p => `<span class="${t >= p.t0 ? 'dicha' : ''}${t >= p.t0 && t < p.t1 ? ' actual' : ''}">${p.txt}</span>`).join(' ');
    SUB.style.opacity = 1;
    SUB.style.transform = `translateX(-50%) scale(${0.92 + 0.08 * rampa(t, g.t0, 0.12)})`;
  } else SUB.style.opacity = 0;
}
window.renderAt = renderAt;
window.__depurar = { scene, LINEAS, FLECHAS, renderer };   // para medir rendimiento desde la consola
renderAt(window.__hfThreeTime || 0);
avisarListo(renderAt);
window.motorListo = true;
