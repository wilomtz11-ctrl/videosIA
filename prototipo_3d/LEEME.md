# Prototipo 3D · "¿Por qué Bolivia no tiene mar?" (14 s)

Globo terráqueo 3D con imagen satelital y atmósfera. La cámara baja del espacio a Sudamérica,
**Bolivia se ilumina**, la cámara vuela en picada sobre **los Andes con relieve real** hasta Atacama,
el **litoral boliviano** brilla y en 1884 **pasa a Chile**. Todo con código y herramientas libres.

## Cómo correrlo

Requisitos: Node.js 22+, Python 3.10+, ffmpeg.

```bash
cd prototipo_3d
npm install                    # three.js + playwright (para revisar fotogramas)
npx playwright install chromium   # solo la primera vez (en tu compu)
python preparar_datos.py       # baja relieve, genera textura, máscaras y efectos (assets/)
npm run fotogramas -- 1 6 9 12 # PNG/JPG sueltos en ../salida/ para revisar rápido
npm run render                 # video final: ../salida/prototipo_3d.mp4
```

Para no enviar telemetría a HeyGen: `export HYPERFRAMES_NO_TELEMETRY=1` (en Windows: `set HYPERFRAMES_NO_TELEMETRY=1`).

Tiempos medidos **sin tarjeta gráfica** (4 núcleos): 14 s de video en ~5.6 min. Con GPU (aunque sea integrada)
HyperFrames la detecta sola y va varias veces más rápido.

## Cómo está hecho

| Pieza | Herramienta | Licencia |
|---|---|---|
| Render a MP4, cuadro por cuadro y determinista, con 4 procesos en paralelo | [HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen) | Apache 2.0 |
| Escena 3D: globo, relieve, atmósfera, estrellas | [Three.js](https://threejs.org) | MIT |
| Relieve (alturas) | [Terrain Tiles en AWS](https://registry.opendata.aws/terrain-tiles) (Mapzen/Tilezen: SRTM, GMTED, ETOPO1) | Libre con atribución |
| Color satelital | NASA Blue Marble | Dominio público |
| Fronteras actuales | [Natural Earth](https://www.naturalearthdata.com) | Dominio público |
| Litoral de 1878 | historical-basemaps (A. Ourednik), calculado con `videosia.geo` | GPL-3.0 |
| Tipografía | Montserrat | OFL |
| Efectos de sonido | sintetizados por `videosia/audio.py` | propios |

Trucos clave:
- **Textura en alta resolución hecha por nosotros**: color de Blue Marble × sombreado calculado del relieve
  (técnica cartográfica clásica). Se ven las quebradas de Atacama y el salar de Uyuni aunque la foto base sea de baja resolución.
- **El relieve se desplaza en la GPU** (shader): la exageración vertical se anima y las montañas "crecen" al acercarse.
- **Máscaras** (Bolivia, litoral) dibujadas en una textura: el shader las ilumina, las pinta y las levanta sin geometría extra.
- **Determinista**: todo depende solo del tiempo `t` (`renderAt(t)`), sin `Math.random()` ni relojes.
  HyperFrames manda un evento `hf-seek` por cuadro y espera a que terminen las cargas de Three.js.
- La cámara se define por tomas `[segundo, lon, lat, altitud, inclinación, rumbo]` en `TOMAS`.

## Investigación (octubre 2026): por qué esta combinación

| Opción | Veredicto |
|---|---|
| **HyperFrames** (Apache 2.0, abril 2026) | ✅ Elegido. HTML → MP4 determinista, adaptador para Three.js, procesos en paralelo, mezcla de audio, verificador de diseño (detecta textos encimados). Pensado para que lo use un agente de IA |
| Remotion | ❌ Gratis para personas, pero **no es software libre** (licencia "source-available"; empresas de 4+ personas pagan) |
| Motion Canvas / Revideo (MIT) | Buenos para 2D; Revideo quedó en segundo plano (su equipo pasó a Midrender) |
| **MapLibre GL** (BSD) globo + relieve | Se ve espectacular, pero sin GPU tarda 20–60 s por cuadro. Útil en una compu con GPU; HyperFrames permite esperar sus teselas con `waitUntil` |
| deck.gl (MIT) | Su capa de relieve no funciona en vista de globo |
| GSAP | ❌ Gratis pero **no libre** (licencia propia). Usamos animación propia y, si hace falta, anime.js (MIT) |
| Blender (GPL) | Calidad de cine, pero demasiado lento sin GPU |
| Theatre.js | Núcleo Apache 2.0, pero su editor es AGPL; no hace falta por ahora |

Imágenes satelitales mejores para usar en tu compu (aquí estaban bloqueadas): NASA Blue Marble original de 21600×10800
(dominio público), NASA GIBS (dominio público) y Sentinel-2 cloudless de EOX (CC BY 4.0, ediciones 2018 en adelante;
la de 2016 es no comercial).
