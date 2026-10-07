# Fábrica de videos de mapas 3D — guía para agentes

Canal "Geografía explicada": videos educativos en español que responden una pregunta con mapas 3D
(globo, relieve real, mapas históricos). Objetivo: el usuario pega una idea o un guion y sale el MP4.

## Flujo para crear un episodio

1. **Investigar** con fuentes confiables (enciclopedias, organismos oficiales, tratados, sitios académicos;
   Wikipedia solo como apoyo). Cada fecha, cifra o nombre del guion debe tener fuente en `publicacion.fuentes`.
   En temas de fronteras: narrar hechos, sin tomar partido ni usar lenguaje despectivo.
2. **Escribir** `episodios/<tema>.yaml` a partir de `episodios/PLANTILLA.yaml` (ejemplo completo: `bolivia_mar.yaml`).
   Retención: gancho en la 1.ª frase (paradoja o dato sorprendente), bucle abierto en la 2.ª, una escena cada 5–9 s,
   reenganche a mitad ("pero la historia no terminó ahí"), cierre con pregunta para comentarios. Mínimo 60 s.
   Números menores de mil escritos con letras en `voz` (la voz los lee mejor); años con cifras.
3. `python -m fabrica validar episodios/<tema>.yaml` (con ElevenLabs dice cuántos créditos costaría la voz).
   La voz se guarda POR FRASE en `biblioteca/voz/frases/`: solo se pagan frases nuevas o cambiadas. Si hay que pagar,
   los comandos se detienen y piden `--si`; usarlo solo con el visto bueno del usuario (borradores gratis: `--voz kokoro`).
4. `python -m fabrica previa episodios/<tema>.yaml <seg> <seg> ...` y revisar los JPG en `salida/previa/`
   (etiquetas fuera de cuadro, textos encimados, encuadres).
5. `python -m fabrica video episodios/<tema>.yaml` → `salida/<tema>.mp4` + `salida/<tema>_descripcion.txt`.

## Arquitectura

- `fabrica/` (Python) orquesta y contiene **toda la lógica de tiempos** (probada en `tests/`):
  `modelo.py` (esquema pydantic del YAML) · `lugares.py` (nombres → coordenadas, Natural Earth) ·
  `terreno.py` (relieve AWS + textura) · `capas.py` (máscaras de formas, mapas políticos por año, fronteras) ·
  `voz.py` (Kokoro ONNX por frase → tiempos de palabras) · `linea_tiempo.py` (compila `escena.json`) ·
  `audio.py` (efectos sintetizados + mezcla) · `construir.py` (pipeline, HyperFrames, ffmpeg).
- `motor3d/` (JavaScript, Three.js): `motor.js` solo dibuja `datos/escena.json` en función de `t` (determinista:
  sin `Math.random` ni relojes). `plantilla.html` es la composición de HyperFrames.
- `build/<tema>/` es el proyecto HyperFrames generado; `datos/` y `modelos/` son cachés (no van a git).
- `videosia/` + `construir_2d.py`: motor 2D antiguo (Skia), se mantiene como respaldo.

## Reglas

- Solo herramientas y datos libres: HyperFrames (Apache 2.0), Three.js (MIT), Kokoro (Apache 2.0),
  AWS Terrain Tiles (atribución), NASA Blue Marble y Natural Earth (dominio público), historical-basemaps (GPL-3.0).
  No usar GSAP ni Remotion (no son libres). Telemetría de HyperFrames desactivada (`HYPERFRAMES_NO_TELEMETRY=1`).
- Antes de commitear: `python -m pytest -q` y `ruff check fabrica tests`.
