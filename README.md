# Geografía explicada · fábrica de videos con mapas animados

Hace videos de mapas animados a partir de un archivo JSON por episodio: la voz marca el ritmo, la cámara
se mueve sola entre escenas y salen subtítulos palabra por palabra, efectos de sonido y una descripción con fuentes.

- **Vertical 1080×1920** para TikTok, Reels y Shorts, o **horizontal 1920×1080** para YouTube largo.
- Sin costo por video: todo es código y datos abiertos.
- Primer episodio: `episodios/bolivia_mar.json` → *¿Por qué Bolivia no tiene mar?* (~90 s).

La estrategia de nicho, las plataformas y los riesgos están en [ESTRATEGIA.md](ESTRATEGIA.md).

**Nuevo:** motor 3D (globo terráqueo, relieve real, cámara que vuela) en [prototipo_3d/](prototipo_3d/LEEME.md), con HyperFrames + Three.js, todo libre.

---

## 1. Instalar (una vez)

1. **Python 3.10+** y **ffmpeg** en el PATH.
   Windows: `winget install Gyan.FFmpeg`. Mac: `brew install ffmpeg`.
2. En la carpeta del proyecto:
   ```bash
   pip install -r requirements.txt
   ```
Las fronteras históricas se descargan solas la primera vez, en `datos/`.

## 2. Hacer un video

```bash
# Vista previa rápida (sin voz, con la duración estimada)
python construir.py episodios/bolivia_mar.json

# Revisar fotogramas sueltos (segundos 1, 20 y 45) antes de renderizar todo
python construir.py episodios/bolivia_mar.json --fotogramas 1 20 45

# Video final con voz
python construir.py episodios/bolivia_mar.json --voz kokoro      # gratis, en tu CPU
python construir.py episodios/bolivia_mar.json --voz archivos    # tus WAV (grabados o de Colab)

# Versión horizontal para YouTube
python construir.py episodios/bolivia_mar.json --formato horizontal
```

El resultado queda en `salida/`: el MP4, la mezcla de audio y `*_descripcion.txt`, con el título, las fuentes y los hashtags listos para copiar.

## 3. Voz (sin tarjeta NVIDIA)

| Opción | Calidad | Dónde corre | Cómo |
|---|---|---|---|
| **Chatterbox en Google Colab** | ★★★★★, clona tu voz | GPU gratis de Google | Abre `colab_voz.ipynb` en [colab.research.google.com](https://colab.research.google.com) (Archivo → Subir cuaderno) y ejecuta las celdas |
| **Kokoro** | ★★★ | Tu CPU, rápido | `pip install kokoro` + instalar [espeak-ng](https://github.com/espeak-ng/espeak-ng/releases); luego `--voz kokoro` (voces: `em_alex`, `ef_dora`, `em_santa`) |
| **Tu propia voz** | La mejor para monetizar | Micrófono | Graba un WAV por escena en `voz/<episodio>/NN_<id>.wav` y usa `--voz archivos` |
| Chatterbox en CPU | ★★★★★ | Tu CPU, lento (varios minutos) | `pip install chatterbox-tts`; luego `--voz chatterbox --referencia mi_voz.wav` |

Licencias: Chatterbox es MIT y Kokoro es Apache 2.0; las dos permiten uso comercial. **No uses** Piper (la mayoría de sus voces
en español son no comerciales), Coqui XTTS (licencia no comercial) ni Edge-TTS (uso no oficial de un servicio de Microsoft).

Si cambias el texto de una escena, solo se regenera esa voz.

## 4. Crear un episodio nuevo

Copia `episodios/bolivia_mar.json` y edítalo. Las piezas:

| Campo | Para qué |
|---|---|
| `region` | `[lon_min, lat_min, lon_max, lat_max]`: zona de la que se cargan fronteras |
| `mapas` | Estados del mapa: `{"1878": {"anio": 1878}, "hoy": {"anio": 2010}}`. Años disponibles: [lista](https://github.com/aourednik/historical-basemaps/tree/master/geojson) |
| `colores` | Color por país (nombre en inglés, como en los datos) |
| `formas` | Zonas calculadas: `{"op": "interseccion", "a": "1878:Bolivia", "b": "2010:Chile", "filtro": [...]}` = lo que era de Bolivia en 1878 y hoy es de Chile. Ops: `interseccion`, `diferencia`, `union`, `pais` |
| `grupos_etiquetas` | Etiquetas reutilizables; en una escena se citan como `"@paises"` |
| `escenas` | La historia, en orden (ver abajo) |
| `publicacion` | Título, descripción, fuentes y hashtags para la descripción |

Cada escena:

```json
{
  "id": "resultado",
  "narracion": "Lo que dice la voz. La duración de la escena sale de este audio.",
  "mapa": "1878",                       // si cambia respecto a la escena anterior → fundido
  "anio": 1884,                         // número (cuenta animada) o texto ("HOY")
  "camara": {"centro": [-67.5, -20.5], "alto": 31, "mov": 1.4},   // alto = grados visibles en vertical
  "texto": {"texto": "Titular en pantalla", "estilo": "alerta|nota|dato", "retraso": 1.0},
  "etiquetas": ["@paises", {"texto": "Arica", "lon": -70.3, "lat": -18.5, "estilo": "punto|claro|pais"}],
  "destacar": [{"forma": "litoral", "color": "#4CC9F0", "retraso": 1.0}],   // brillo que palpita
  "pintar":   [{"forma": "litoral", "color": "#E5534B", "retraso": 0.9}],   // cambio de dueño (persiste)
  "anillos":  [{"lon": -70.4, "lat": -23.6, "color": "#FF4D4F", "radio": 80}],
  "flechas":  [{"de": [-72.3, -33.0], "a": [-70.7, -23.9], "color": "#FF4D4F", "curva": -0.25}],
  "efectos":  ["impacto"]                // además de whoosh y pop, que son automáticos
}
```

Truco: renderiza con `--fotogramas` para ajustar posiciones y encuadres en segundos, y deja el video completo para el final.

## 5. Estructura

```
construir.py          programa principal
videosia/geo.py       fronteras históricas, caché y formas derivadas
videosia/render.py    dibujo de cada fotograma (Skia)
videosia/linea_tiempo.py  cámara, fundidos, subtítulos y efectos en el tiempo
videosia/voz.py       motores de voz
videosia/audio.py     efectos sintetizados y mezcla con música
episodios/            un JSON por video
colab_voz.ipynb       voz con GPU gratis en Google Colab
fuentes/              Montserrat (licencia OFL)
demo_original/        la primera demo (Sudamérica, 30 s)
```

## Créditos y licencias de datos

- Fronteras: [historical-basemaps](https://github.com/aourednik/historical-basemaps), de André Ourednik (GPL-3.0). Son aproximadas;
  el crédito aparece en cada video. Hay errores conocidos (por ejemplo, en los mapas de 1880 y 1900 Bolivia todavía tiene costa),
  por eso el episodio de Bolivia usa 1878 y 2010 y calcula las zonas perdidas.
- Tipografía: [Montserrat](https://github.com/JulietaUla/Montserrat) (SIL Open Font License).
- Efectos de sonido: sintetizados por el propio código, sin derechos de terceros.
