# Geografía explicada · fábrica de videos de mapas 3D

Escribes (o pegas) un guion en YAML y sale un video listo para publicar: globo terráqueo 3D, relieve real,
mapas históricos, cámara que vuela, voz, subtítulos palabra por palabra, efectos de sonido y una descripción con fuentes.

- **Vertical 1080×1920** (TikTok, Reels, Shorts) u **horizontal 1920×1080** (YouTube).
- **Todo libre y gratuito**: código abierto y datos abiertos, sin pagar por video.
- Primer episodio: [`episodios/bolivia_mar.yaml`](episodios/bolivia_mar.yaml) → *¿Por qué Bolivia no tiene mar?* (~2:13).

Estrategia de nicho, plataformas, riesgos y tecnologías elegidas: [ESTRATEGIA.md](ESTRATEGIA.md).

---

## 1. Instalar (una vez)

Requisitos: **Python 3.10+**, **Node.js 22+** y **ffmpeg** en el PATH
(Windows: `winget install OpenJS.NodeJS Gyan.FFmpeg`; Mac: `brew install node ffmpeg`).

```bash
pip install -r requirements.txt
cd motor3d && npm install && npx playwright install chromium && cd ..
```

La primera vez se descargan solos el modelo de voz (~350 MB), el relieve de la región y los mapas.
Todo queda en caché (`modelos/`, `datos/`).

## 2. Hacer un video

```bash
python -m fabrica validar episodios/bolivia_mar.yaml               # revisa el guion (instantáneo)
python -m fabrica previa  episodios/bolivia_mar.yaml 2 30 60 90    # fotogramas sueltos en salida/previa/ (segundos)
python -m fabrica video   episodios/bolivia_mar.yaml               # video final: salida/bolivia_mar.mp4
python -m fabrica video   episodios/bolivia_mar.yaml --borrador    # más rápido (sin antialiasing, calidad baja)
```

Junto al video sale `salida/<tema>_descripcion.txt` con el título, las fuentes, los créditos y los hashtags.

**Tiempos de referencia** (4 núcleos, **sin** tarjeta gráfica): voz ~3× más rápida que tiempo real; render
~1 fotograma/s (≈1 h para 2 minutos de video). Con GPU, aunque sea integrada, HyperFrames la usa sola y va varias veces más rápido.
También puedes renderizar en Google Colab con GPU gratis: [`colab.ipynb`](colab.ipynb).

## 3. Crear un episodio nuevo

Copia [`episodios/PLANTILLA.yaml`](episodios/PLANTILLA.yaml) (explica cada campo). Lo esencial de una escena:

```yaml
- voz: Lo que dice la narración. La escena dura lo que dure la voz.
  camara: {ir_a: Calama, altura: cerca, inclinacion: 55, rumbo: 65}   # nombres o [lon, lat]
  anio: 1879
  titular: {texto: 23 de marzo de 1879, estilo: nota}
  etiquetas: [Calama]
  anillos: [Calama]
```

Los nombres ("Bolivia", "Calama", "Lago Titicaca", "Océano Pacífico") se convierten solos en coordenadas.
Las **formas** resaltan o "pintan" zonas, incluso calculadas: lo que en 1878 era de Bolivia y hoy es de Chile.

Recetas de retención del ejemplo: paradoja en la primera frase, bucle abierto ("empieza con 10 centavos y termina
en una guerra"), un corte cada 5–9 s, reenganche a mitad del video y cierre con pregunta para comentarios.

Con Claude: pega la idea o el guion en una sesión; `CLAUDE.md` le explica cómo investigar, escribir el YAML y renderizar.

## 4. Voz

| Motor | Calidad | Dónde corre | Uso |
|---|---|---|---|
| `kokoro` (por defecto) | ★★★ | CPU | Voces `em_alex`, `em_santa`, `ef_dora`. Apache 2.0 |
| `chatterbox` | ★★★★★, clona tu voz | GPU (Colab gratis) | `voz: {motor: chatterbox, referencia: mi_voz.wav}`. MIT |
| `archivos` | La mejor: tu voz | Micrófono | Un WAV por escena en `voz/<tema>/NN_<id>.wav` |
| `estimar` | Sin voz | — | Para revisar rápido: `--voz estimar` |

## 5. Cómo está hecho

```
episodios/*.yaml ─► fabrica (Python) ──────────────────────────────► build/<tema>/ ─► HyperFrames ─► MP4 + audio
                    validar · lugares · relieve · capas · voz ·        escena.json +    Chromium, 4 procesos
                    línea de tiempo · audio                            motor3d/motor.js
```

- **Python** tiene toda la lógica de tiempos (probada con `pytest`); el **motor 3D** (Three.js) solo dibuja
  `escena.json` en función del tiempo, así cada fotograma sale idéntico en cada render.
- La textura de alta resolución se fabrica con el color de NASA Blue Marble y el sombreado del relieve
  (AWS Terrain Tiles); el relieve se desplaza en la GPU; las zonas se iluminan con máscaras en el shader.

| Pieza | Herramienta | Licencia |
|---|---|---|
| Render HTML → MP4 determinista | [HyperFrames](https://github.com/heygen-com/hyperframes) | Apache 2.0 |
| 3D | [Three.js](https://threejs.org) | MIT |
| Voz | [Kokoro-82M (ONNX)](https://github.com/thewh1teagle/kokoro-onnx) | Apache 2.0 / MIT |
| Relieve | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles) (Mapzen) | Libre con atribución |
| Imagen satelital | NASA Blue Marble | Dominio público |
| Fronteras y lugares | [Natural Earth](https://www.naturalearthdata.com) | Dominio público |
| Mapas históricos | [historical-basemaps](https://github.com/aourednik/historical-basemaps) | GPL-3.0 |
| Tipografía | Montserrat | OFL |

## 6. Desarrollo

```bash
python -m pytest -q            # tests
ruff check fabrica tests       # estilo
```

El motor 2D original (Skia) sigue disponible: `python construir_2d.py episodios/bolivia_mar_2d.json`.
