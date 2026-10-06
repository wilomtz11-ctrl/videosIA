"""Narración: un WAV por escena + tiempos de cada palabra (para los subtítulos).

Se sintetiza frase por frase: así se conoce el inicio y fin exacto de cada frase, y dentro de
cada frase las palabras se reparten por sílabas (error típico < 0.15 s, suficiente para karaoke).

Motores:
  kokoro      Kokoro-82M en ONNX (Apache 2.0). CPU, ~3x tiempo real. Voces: em_alex, em_santa, ef_dora
  chatterbox  Chatterbox Multilingual (MIT). Clona voz con 'referencia'. Mejor con GPU (Colab)
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


def _chatterbox(texto, cfg):
    if "chatterbox" not in _motores:
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        disp = "cuda" if torch.cuda.is_available() else "cpu"
        _motores["chatterbox"] = ChatterboxMultilingualTTS.from_pretrained(device=disp)
    m = _motores["chatterbox"]
    extra = {"audio_prompt_path": cfg.referencia} if cfg.referencia else {}
    wav = m.generate(texto, language_id="es", **extra)
    return _remuestrear(wav.squeeze(0).cpu().numpy(), m.sr)


def _palabras(frase, t0, t1):
    pal = frase.split()
    pesos = [silabas(p) + 0.3 + (1.5 if p[-1] in ",;:" else 0) for p in pal]   # las comas llevan una pausa
    total, t, out = sum(pesos), t0, []
    for p, w in zip(pal, pesos):
        d = (t1 - t0) * w / total
        out.append({"txt": p, "t0": round(t, 3), "t1": round(t + d, 3)})
        t += d
    return out


def sintetizar_escena(texto: str, cfg) -> tuple[np.ndarray, list[dict]]:
    """Devuelve (audio 24 kHz, palabras con tiempos relativos al inicio del audio)."""
    if cfg.motor == "estimar":
        dur = max(1.5, len(texto) / 15.0)
        return np.zeros(int(dur * SR), np.float32), _palabras(texto, 0.0, dur)
    sintetizar = {"kokoro": _kokoro, "chatterbox": _chatterbox}[cfg.motor]
    trozos, palabras, t = [], [], 0.0
    for fr in frases(texto):
        a = _recortar(sintetizar(fr, cfg))
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
    salida = []
    for i, esc in enumerate(escenas):
        wav = carpeta / f"{i + 1:02d}_{esc.id}.wav"
        meta = wav.with_suffix(".json")
        huella = hashlib.sha1(json.dumps([cfg.motor, cfg.voz, cfg.velocidad, cfg.referencia, esc.voz]).encode()).hexdigest()
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
        audio, palabras = sintetizar_escena(esc.voz, cfg)
        sf.write(wav, audio, SR)
        dur = len(audio) / SR
        meta.write_text(json.dumps({"huella": huella, "duracion": dur, "palabras": palabras}, ensure_ascii=False), encoding="utf-8")
        print(f"  voz {wav.name}: {dur:.1f} s")
        salida.append({"wav": wav, "duracion": dur, "palabras": palabras})
    return salida
