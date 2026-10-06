"""Voz en off: un audio por escena.

Motores:
  estimar     silencio con la duración aproximada (para previsualizar sin voz)
  archivos    usa WAV ya hechos (grabados por ti, o generados en Colab)
  kokoro      Kokoro-82M (Apache 2.0). Corre bien en CPU
  chatterbox  Chatterbox Multilingual (MIT). Clona voz. Mejor con GPU (Colab), lento en CPU

Cada escena queda en voz/<episodio>/<NN>_<id>.wav. Si el texto no cambió, no se regenera.
"""
import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf

CARACTERES_POR_SEGUNDO = 15.0
_modelos = {}


def _huella(texto, motor, opciones):
    return hashlib.sha1(f"{motor}|{sorted(opciones.items())}|{texto}".encode()).hexdigest()[:12]


def _kokoro(texto, op):
    from kokoro import KPipeline
    if "kokoro" not in _modelos:
        _modelos["kokoro"] = KPipeline(lang_code="e", repo_id="hexgrad/Kokoro-82M")
    trozos = [a for _, _, a in _modelos["kokoro"](texto, voice=op.get("voz", "em_alex"), speed=op.get("velocidad", 1.0))]
    audio = np.concatenate([np.asarray(t, dtype=np.float32) for t in trozos])
    return audio, 24000


def _chatterbox(texto, op):
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    if "chatterbox" not in _modelos:
        disp = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  cargando Chatterbox en {disp}...")
        _modelos["chatterbox"] = ChatterboxMultilingualTTS.from_pretrained(device=disp)
    m = _modelos["chatterbox"]
    extra = {}
    if op.get("referencia"):
        extra["audio_prompt_path"] = op["referencia"]
    wav = m.generate(texto, language_id="es", exaggeration=op.get("emocion", 0.5),
                     cfg_weight=op.get("cfg", 0.5), **extra)
    return wav.squeeze(0).cpu().numpy().astype(np.float32), m.sr


def generar(episodio, escenas, motor, opciones, carpeta):
    """Genera (o reutiliza) el audio de cada escena. Devuelve [(ruta, duración_s)]."""
    carpeta = Path(carpeta) / episodio
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = []
    for i, esc in enumerate(escenas):
        texto = esc["narracion"].strip()
        ruta = carpeta / f"{i:02d}_{esc['id']}.wav"
        marca = ruta.with_suffix(".txt")
        huella = _huella(texto, motor, opciones)
        if motor == "archivos":
            if not ruta.exists():
                raise FileNotFoundError(f"Falta {ruta}. Grábalo o genéralo en Colab (ver README).")
        elif not (ruta.exists() and marca.exists() and marca.read_text(encoding="utf-8").startswith(huella)):
            if motor == "estimar":
                audio, sr = np.zeros(int(max(1.5, len(texto) / CARACTERES_POR_SEGUNDO) * 24000), np.float32), 24000
            elif motor == "kokoro":
                audio, sr = _kokoro(texto, opciones)
            elif motor == "chatterbox":
                audio, sr = _chatterbox(texto, opciones)
            else:
                raise ValueError(f"Motor de voz desconocido: {motor}")
            sf.write(ruta, audio, sr)
            marca.write_text(f"{huella}\n{texto}\n", encoding="utf-8")
            print(f"  voz {ruta.name}: {len(audio) / sr:.1f} s")
        salida.append((ruta, sf.info(str(ruta)).duration))
    return salida
