"""Cliente de ElevenLabs con biblioteca reutilizable (ahorro de créditos).

Todo lo generado se guarda en biblioteca/ (va a git) con un índice. Si se vuelve a pedir lo mismo
(mismo texto/voz/ajustes, mismo efecto, misma música), se reutiliza sin gastar créditos,
aunque el entorno sea nuevo.

  biblioteca/voz/<hash>.mp3 + .json   narración con tiempos por carácter
  biblioteca/sonidos/<hash>.mp3        efectos y ambientes
  biblioteca/musica/<hash>.mp3         música
  biblioteca/indice.json               qué es cada archivo, prompt y créditos aproximados
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import datos

API = "https://api.elevenlabs.io/v1"
BIBLIOTECA = datos.RAIZ / "biblioteca"
INDICE = BIBLIOTECA / "indice.json"


def _clave() -> str:
    clave = os.environ.get("ELEVENLABS_API_KEY")
    if not clave:
        raise RuntimeError("Falta la variable de entorno ELEVENLABS_API_KEY")
    return clave


def _post(ruta: str, cuerpo: dict, timeout=300) -> bytes:
    req = urllib.request.Request(f"{API}{ruta}", data=json.dumps(cuerpo).encode(),
                                 headers={"xi-api-key": _clave(), "Content-Type": "application/json"})
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and intento < 2:   # saturación: reintento con espera
                time.sleep(5 * (intento + 1))
                continue
            raise RuntimeError(f"ElevenLabs respondió {e.code}: {e.read()[:300].decode(errors='replace')}") from e
    raise RuntimeError("ElevenLabs no respondió")


def _huella(*partes) -> str:
    return hashlib.sha1(json.dumps(partes, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _registrar(clave: str, entrada: dict):
    indice = json.loads(INDICE.read_text(encoding="utf-8")) if INDICE.exists() else {}
    indice[clave] = {**entrada, "fecha": time.strftime("%Y-%m-%d")}
    INDICE.write_text(json.dumps(indice, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def creditos() -> dict:
    req = urllib.request.Request(f"{API}/user/subscription", headers={"xi-api-key": _clave()})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    return {"usados": d["character_count"], "limite": d["character_limit"], "restantes": d["character_limit"] - d["character_count"]}


def narracion(texto: str, voz: str, modelo: str, estabilidad: float, estilo: float,
              solo_biblioteca: bool = False) -> tuple[Path, dict] | None:
    """MP3 de la narración + alineación por carácter. Reutiliza la biblioteca si ya existe.
    Con solo_biblioteca=True nunca llama a la API (devuelve None si no está guardada)."""
    h = _huella("voz", texto, voz, modelo, estabilidad, estilo)
    mp3, meta = BIBLIOTECA / "voz" / f"{h}.mp3", BIBLIOTECA / "voz" / f"{h}.json"
    if mp3.exists() and meta.exists():
        return mp3, json.loads(meta.read_text(encoding="utf-8"))
    if solo_biblioteca:
        return None
    cuerpo = {"text": texto, "model_id": modelo, "language_code": "es",
              "voice_settings": {"stability": estabilidad, "similarity_boost": 0.8, "style": estilo, "use_speaker_boost": True}}
    d = json.loads(_post(f"/text-to-speech/{voz}/with-timestamps?output_format=mp3_44100_128", cuerpo))
    mp3.parent.mkdir(parents=True, exist_ok=True)
    mp3.write_bytes(base64.b64decode(d["audio_base64"]))
    alineacion = d.get("alignment") or d["normalized_alignment"]
    meta.write_text(json.dumps(alineacion, ensure_ascii=False), encoding="utf-8")
    _registrar(f"voz/{h}.mp3", {"tipo": "voz", "texto": texto, "voz": voz, "modelo": modelo, "creditos_aprox": len(texto)})
    return mp3, alineacion


def _nombre(prompt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", prompt.lower())[:40].strip("-")


def efecto(prompt: str, duracion: float | None = None) -> Path:
    """Efecto o ambiente (en inglés funciona mejor). Se reutiliza para todos los episodios."""
    h = _huella("sfx", prompt, duracion)
    mp3 = BIBLIOTECA / "sonidos" / f"{_nombre(prompt)}-{h}.mp3"
    if not mp3.exists():
        cuerpo = {"text": prompt, "prompt_influence": 0.5}
        if duracion:
            cuerpo["duration_seconds"] = round(min(22.0, max(0.5, duracion)), 1)
        mp3.parent.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(_post("/sound-generation?output_format=mp3_44100_128", cuerpo))
        _registrar(f"sonidos/{mp3.name}", {"tipo": "efecto", "prompt": prompt, "duracion": duracion})
        print(f"  efecto nuevo: {prompt[:60]}")
    return mp3


def musica(prompt: str, segundos: float) -> Path:
    """Pista instrumental (~14 créditos/s). Se reutiliza para todos los episodios."""
    segundos = round(min(300, max(10, segundos)))
    h = _huella("musica", prompt, segundos)
    mp3 = BIBLIOTECA / "musica" / f"{_nombre(prompt)}-{h}.mp3"
    if not mp3.exists():
        mp3.parent.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(_post("/music?output_format=mp3_44100_128",
                              {"prompt": prompt + ", instrumental, no vocals", "music_length_ms": segundos * 1000}, timeout=600))
        _registrar(f"musica/{mp3.name}", {"tipo": "musica", "prompt": prompt, "segundos": segundos,
                                          "creditos_aprox": segundos * 14})
        print(f"  música nueva ({segundos} s): {prompt[:60]}")
    return mp3
