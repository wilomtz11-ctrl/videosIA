"""Narración: un WAV por escena + tiempos de cada palabra (para los subtítulos).

Se sintetiza frase por frase: así se conoce el inicio y fin exacto de cada frase, y dentro de
cada frase las palabras se reparten por sílabas (error típico < 0.15 s, suficiente para karaoke).

Motores:
  kokoro      Kokoro-82M en ONNX (Apache 2.0). CPU, ~3x tiempo real. Voces: em_alex, em_santa, ef_dora
  chatterbox  Chatterbox Multilingual (MIT). Expresiva ('emocion' 0.3–1.2) y clona la voz de 'referencia'.
              Corre en su propio entorno (modelos/venv-chatterbox); en CPU ~5 s por segundo de audio
  elevenlabs  ElevenLabs (de pago, la más natural). 'voz' = id de la voz; tiempos exactos por carácter.
              Requiere la variable de entorno ELEVENLABS_API_KEY
  archivos    WAV ya hechos por escena en voz/<episodio>/<id>.wav (tu propia voz)
  estimar     silencio con duración estimada (vista previa rápida)
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from . import datos

SR = 24000
MODELOS = datos.RAIZ / "modelos"
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/{}"
PAUSAS = {".": 0.30, "?": 0.34, "!": 0.30, "…": 0.36}
_motores = {}


def frases(texto: str) -> list[str]:
    """Divide en oraciones (punto, ¿?, ¡!, puntos suspensivos). No corta en comas para no romper la entonación."""
    partes = re.findall(r"[^.?!…]+(?:\.\.\.|[.?!…]+)?", texto)
    return [p.strip() for p in partes if re.search(r"\w", p)]


def silabas(palabra: str) -> int:
    digitos = re.sub(r"\D", "", palabra)
    if digitos:   # los números se leen largos: 1879 = "mil ochocientos setenta y nueve"
        return 9 if len(digitos) == 4 else 2 * len(digitos)
    return max(1, len(re.findall(r"[aeiouáéíóúü]+", palabra.lower())))


def _recortar(audio, umbral=0.012):
    idx = np.where(np.abs(audio) > umbral)[0]
    if len(idx) == 0:
        return audio[:0]
    return audio[max(0, idx[0] - int(0.02 * SR)): idx[-1] + int(0.04 * SR)]


def _remuestrear(x, sr):
    if sr == SR:
        return x.astype(np.float32)
    n = int(len(x) * SR / sr)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def _kokoro(texto, cfg):
    if "kokoro" not in _motores:
        from kokoro_onnx import Kokoro
        modelo = datos.bajar(KOKORO_URL.format("kokoro-v1.0.onnx"), MODELOS / "kokoro-v1.0.onnx")
        voces = datos.bajar(KOKORO_URL.format("voices-v1.0.bin"), MODELOS / "voices-v1.0.bin")
        _motores["kokoro"] = Kokoro(str(modelo), str(voces))
    audio, sr = _motores["kokoro"].create(texto, voice=cfg.voz, speed=cfg.velocidad, lang="es")
    return _remuestrear(np.asarray(audio, np.float32), sr)


PY_CHATTERBOX = MODELOS / "venv-chatterbox" / "bin" / "python"


def _referencia_es() -> Path:
    """Voz de referencia en español para Chatterbox (generada con Kokoro em_alex; sin derechos de terceros)."""
    ruta = MODELOS / "referencia_es_em_alex.wav"
    if not ruta.exists():
        from .modelo import Voz
        txt = ("Hace más de cien años, en el desierto más seco del mundo, comenzó una historia increíble. "
               "Una historia de minerales, tratados y una guerra que cambió el mapa de Sudamérica para siempre.")
        sf.write(ruta, _kokoro(txt, Voz(voz="em_alex", velocidad=1.0)), SR)
    return ruta


def _chatterbox_lote(pendientes: list[dict], cfg) -> None:
    """Sintetiza todas las frases pendientes en un solo proceso (el modelo se carga una vez)."""
    import os
    import subprocess
    import sys
    py = Path(os.environ.get("FABRICA_PY_CHATTERBOX", PY_CHATTERBOX))
    if not py.exists():
        py = Path(sys.executable)   # Chatterbox instalado en el mismo entorno (p. ej. Colab)
    referencia = cfg.referencia or str(_referencia_es())
    pedido = {"referencia": referencia, "items": pendientes}
    print(f"  chatterbox: {len(pendientes)} frases (en CPU ~5 s por segundo de audio)...", flush=True)
    subprocess.run([str(py), str(Path(__file__).with_name("chatterbox_worker.py"))], input=json.dumps(pedido),
                   text=True, check=True, env={**os.environ, "HF_HUB_DISABLE_XET": "1"})


ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voz}/with-timestamps?output_format=mp3_44100_128"


def palabras_desde_alineacion(texto: str, al: dict) -> list[dict]:
    """Tiempos de cada palabra a partir de los tiempos por carácter que devuelve ElevenLabs."""
    chars, ini, fin = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    out, actual = [], None
    for c, a, b in zip(chars, ini, fin):
        if c.isspace():
            if actual:
                out.append(actual)
                actual = None
        elif actual is None:
            actual = {"txt": c, "t0": a, "t1": b}
        else:
            actual["txt"] += c
            actual["t1"] = b
    if actual:
        out.append(actual)
    return [{"txt": w["txt"], "t0": round(w["t0"], 3), "t1": round(w["t1"], 3)} for w in out]


def _elevenlabs(texto: str, cfg) -> tuple[np.ndarray, list[dict]]:
    """Una escena completa (mejor entonación) con tiempos por carácter. Requiere ELEVENLABS_API_KEY."""
    import base64
    import os
    import subprocess
    import urllib.error
    import urllib.request
    clave = os.environ.get("ELEVENLABS_API_KEY")
    if not clave:
        raise RuntimeError("Falta la variable de entorno ELEVENLABS_API_KEY")
    cuerpo = {"text": texto, "model_id": cfg.modelo, "language_code": "es",
              "voice_settings": {"stability": cfg.estabilidad, "similarity_boost": 0.8, "style": cfg.estilo, "use_speaker_boost": True}}
    req = urllib.request.Request(ELEVENLABS_URL.format(voz=cfg.voz), data=json.dumps(cuerpo).encode(),
                                 headers={"xi-api-key": clave, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs respondió {e.code}: {e.read()[:300].decode(errors='replace')}") from e
    mp3 = base64.b64decode(d["audio_base64"])
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", "-", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         input=mp3, capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, dtype=np.float32).copy()
    return audio, palabras_desde_alineacion(texto, d.get("alignment") or d["normalized_alignment"])


def _palabras(frase, t0, t1):
    pal = frase.split()
    pesos = [silabas(p) + 0.3 + (1.5 if p[-1] in ",;:" else 0) for p in pal]   # las comas llevan una pausa
    total, t, out = sum(pesos), t0, []
    for p, w in zip(pal, pesos):
        d = (t1 - t0) * w / total
        out.append({"txt": p, "t0": round(t, 3), "t1": round(t + d, 3)})
        t += d
    return out


def _ruta_frase(carpeta: Path, frase: str, cfg, emocion: float) -> Path:
    h = hashlib.sha1(json.dumps([cfg.motor, cfg.voz, cfg.velocidad, cfg.referencia, emocion, cfg.cfg, frase]).encode()).hexdigest()[:16]
    return carpeta / "frases" / f"{h}.wav"


def _audio_frase(carpeta: Path, frase: str, cfg, emocion: float) -> np.ndarray:
    ruta = _ruta_frase(carpeta, frase, cfg, emocion)
    if not ruta.exists():
        if cfg.motor != "kokoro":
            raise RuntimeError(f"falta la frase sintetizada: {frase!r}")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        sf.write(ruta, _kokoro(frase, cfg), SR)
    a, sr = sf.read(str(ruta), dtype="float32")
    return _remuestrear(a if a.ndim == 1 else a.mean(axis=1), sr)


def sintetizar_escena(texto: str, cfg, carpeta: Path | None = None, emocion: float | None = None) -> tuple[np.ndarray, list[dict]]:
    """Devuelve (audio 24 kHz, palabras con tiempos relativos al inicio del audio)."""
    if cfg.motor == "estimar":
        dur = max(1.5, len(texto) / 15.0)
        return np.zeros(int(dur * SR), np.float32), _palabras(texto, 0.0, dur)
    if cfg.motor == "elevenlabs":
        return _elevenlabs(texto, cfg)
    carpeta = carpeta or MODELOS / "cache_voz"
    emocion = cfg.emocion if emocion is None else emocion
    trozos, palabras, t = [], [], 0.0
    for fr in frases(texto):
        a = _recortar(_audio_frase(carpeta, fr, cfg, emocion))
        dur = len(a) / SR
        palabras += _palabras(fr, t, t + dur)
        pausa = PAUSAS.get(fr.rstrip()[-1], 0.08)
        trozos += [a, np.zeros(int(pausa * SR), np.float32)]
        t += dur + pausa
    audio = np.concatenate(trozos) if trozos else np.zeros(SR, np.float32)
    return audio, palabras


def generar(episodio: str, escenas, cfg, carpeta: Path) -> list[dict]:
    """Por escena: {'wav', 'duracion', 'palabras'}. Reutiliza lo ya generado si el texto no cambió."""
    carpeta = Path(carpeta) / episodio
    carpeta.mkdir(parents=True, exist_ok=True)
    if cfg.motor == "chatterbox":   # primero todas las frases que falten, en un solo lote
        pendientes, vistas = [], set()
        for esc in escenas:
            emo = cfg.emocion if esc.emocion is None else esc.emocion
            for fr in frases(esc.voz):
                ruta = _ruta_frase(carpeta, fr, cfg, emo)
                if not ruta.exists() and ruta not in vistas:
                    vistas.add(ruta)
                    pendientes.append({"texto": fr, "emocion": emo, "cfg": cfg.cfg, "salida": str(ruta)})
        if pendientes:
            (carpeta / "frases").mkdir(parents=True, exist_ok=True)
            _chatterbox_lote(pendientes, cfg)
    salida = []
    for i, esc in enumerate(escenas):
        wav = carpeta / f"{i + 1:02d}_{esc.id}.wav"
        meta = wav.with_suffix(".json")
        emo = cfg.emocion if esc.emocion is None else esc.emocion
        huella = hashlib.sha1(json.dumps([cfg.motor, cfg.voz, cfg.velocidad, cfg.referencia, emo, cfg.cfg, esc.voz]
                                         + ([cfg.modelo, cfg.estabilidad, cfg.estilo] if cfg.motor == "elevenlabs" else [])
                                         ).encode()).hexdigest()
        if cfg.motor == "archivos":
            if not wav.exists():
                raise FileNotFoundError(f"Falta {wav} (graba tu voz para esa escena)")
            dur = sf.info(str(wav)).duration
            salida.append({"wav": wav, "duracion": dur, "palabras": _palabras(esc.voz, 0, dur)})
            continue
        if meta.exists() and wav.exists():
            m = json.loads(meta.read_text(encoding="utf-8"))
            if m.get("huella") == huella:
                salida.append({"wav": wav, "duracion": m["duracion"], "palabras": m["palabras"]})
                continue
        audio, palabras = sintetizar_escena(esc.voz, cfg, carpeta, emo)
        sf.write(wav, audio, SR)
        dur = len(audio) / SR
        meta.write_text(json.dumps({"huella": huella, "duracion": dur, "palabras": palabras}, ensure_ascii=False), encoding="utf-8")
        print(f"  voz {wav.name}: {dur:.1f} s")
        salida.append({"wav": wav, "duracion": dur, "palabras": palabras})
    return salida
