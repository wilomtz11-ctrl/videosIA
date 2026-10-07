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


def palabras_desde_alineacion(texto: str, al: dict) -> list[dict]:
    """Tiempos de cada palabra a partir de los tiempos por carácter que devuelve ElevenLabs."""
    chars, ini, fin = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    out, actual, en_etiqueta = [], None, False
    for c, a, b in zip(chars, ini, fin):
        if c == "[":            # las etiquetas de tono de v3 ([mysterious]) no van en los subtítulos
            en_etiqueta = True
            continue
        if en_etiqueta:
            en_etiqueta = c != "]"
            continue
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


def con_tono(texto: str, tono: str | None) -> str:
    """Antepone la etiqueta de emoción de ElevenLabs v3 (p. ej. [mysterious])."""
    if not tono:
        return texto
    from .modelo import TONOS
    return f"[{TONOS.get(tono.lower(), tono)}] {texto}"


def _decodificar(mp3: Path) -> np.ndarray:
    import subprocess
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, dtype=np.float32).copy()


# ---------- ElevenLabs: biblioteca por FRASE ----------
# Cada frase narrada se guarda por separado en biblioteca/voz/frases/. Así:
#  - si cambias una frase del guion, solo se paga esa frase (no la escena entera);
#  - las frases que se repiten entre episodios (cierres, llamadas a comentar) salen gratis;
#  - lo ya pagado nunca se vuelve a pagar, aunque el entorno sea nuevo (va a git).
# Las frases que faltan y van seguidas se piden juntas en una sola llamada (mejor entonación).

def _dir_frases() -> Path:
    from . import elevenlabs
    return elevenlabs.BIBLIOTECA / "voz" / "frases"


def _clave_frase(frase: str, cfg, tono: str | None) -> str:
    return hashlib.sha1(json.dumps(["frase", frase, cfg.voz, cfg.modelo, cfg.estabilidad, cfg.estilo, tono],
                                   ensure_ascii=False).encode()).hexdigest()[:16]


def _frase_guardada(frase: str, cfg, tono: str | None):
    base = _dir_frases() / _clave_frase(frase, cfg, tono)
    audio, meta = base.with_suffix(".ogg"), base.with_suffix(".json")
    if not (audio.exists() and meta.exists()):
        return None
    a, sr = sf.read(str(audio), dtype="float32")
    return _remuestrear(a, sr), json.loads(meta.read_text(encoding="utf-8"))["palabras"]


def _guardar_frase(frase: str, cfg, tono: str | None, audio: np.ndarray, palabras: list[dict]):
    base = _dir_frases() / _clave_frase(frase, cfg, tono)
    base.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(base.with_suffix(".ogg")), audio, SR, format="OGG", subtype="VORBIS")
    base.with_suffix(".json").write_text(json.dumps({"texto": frase, "tono": tono, "palabras": palabras},
                                                    ensure_ascii=False), encoding="utf-8")


def _tono_v3(cfg, tono):
    return tono if cfg.modelo == "eleven_v3" else None


def trocear(texto_voz: str, frs: list[str], audio: np.ndarray, al: dict):
    """Parte una narración en sus frases usando los tiempos por carácter.
    Cada corte cae a mitad del silencio entre frases, así al volver a unirlas suena igual.
    Devuelve [(audio, palabras relativas)] o None si la alineación no cuadra."""
    chars, ini, fin = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    if "".join(chars) != texto_voz:
        return None
    rangos, pos = [], 0
    for fr in frs:
        k = texto_voz.find(fr, pos)
        if k < 0:
            return None
        rangos.append((k, k + len(fr)))
        pos = k + len(fr)
    palabras = palabras_desde_alineacion(texto_voz, al)
    cuentas = [len(fr.split()) for fr in frs]
    if sum(cuentas) != len(palabras):
        return None
    total = len(audio) / SR
    cortes = [0.0] + [(fin[rangos[i][1] - 1] + ini[rangos[i + 1][0]]) / 2 for i in range(len(frs) - 1)] + [total]
    out, w = [], 0
    for i, n in enumerate(cuentas):
        c0, c1 = cortes[i], cortes[i + 1]
        pal = [{"txt": x["txt"], "t0": round(x["t0"] - c0, 3), "t1": round(x["t1"] - c0, 3)} for x in palabras[w:w + n]]
        out.append((audio[int(round(c0 * SR)):int(round(c1 * SR))], pal))
        w += n
    return out


def _plan_elevenlabs(texto: str, cfg, tono: str | None):
    """Qué frases ya están guardadas y qué tramos hay que pedir. Devuelve (frases, clips, pedidos)
    con pedidos = [(indices, texto a enviar)]; si la escena entera ya estaba guardada, sale gratis."""
    frs = frases(texto)
    clips = [_frase_guardada(f, cfg, tono) for f in frs]
    faltan = [i for i, c in enumerate(clips) if c is None]
    if not faltan:
        return frs, clips, []
    if len(faltan) == len(frs):   # escena nueva (o guardada entera en el formato anterior)
        return frs, clips, [(faltan, texto)]
    grupos, actual = [], [faltan[0]]
    for i in faltan[1:]:
        if i == actual[-1] + 1:
            actual.append(i)
        else:
            grupos.append(actual)
            actual = [i]
    grupos.append(actual)
    return frs, clips, [(g, " ".join(frs[i] for i in g)) for g in grupos]


def creditos_voz(texto: str, cfg, tono: str | None = None) -> int:
    """Créditos que costaría narrar este texto ahora (0 si todo está en la biblioteca)."""
    from . import elevenlabs
    tono = _tono_v3(cfg, tono)
    _, _, pedidos = _plan_elevenlabs(texto, cfg, tono)
    total = 0
    for _, txt in pedidos:
        tv = con_tono(txt, tono)
        if elevenlabs.narracion(tv, cfg.voz, cfg.modelo, cfg.estabilidad, cfg.estilo, solo_biblioteca=True) is None:
            total += len(tv)
    return total


def _elevenlabs(texto: str, cfg, tono: str | None = None) -> tuple[np.ndarray, list[dict]]:
    """Una escena con tiempos por carácter, armada con frases de la biblioteca; solo se pide lo que falta."""
    from . import elevenlabs
    tono = _tono_v3(cfg, tono)
    frs, clips, pedidos = _plan_elevenlabs(texto, cfg, tono)
    for indices, txt in pedidos:
        tv = con_tono(txt, tono)
        mp3, al = elevenlabs.narracion(tv, cfg.voz, cfg.modelo, cfg.estabilidad, cfg.estilo)
        audio = _decodificar(mp3)
        partes = trocear(tv, [frs[i] for i in indices], audio, al)
        if partes is None:   # alineación rara: se usa el tramo entero sin partir
            clips[indices[0]] = (audio, palabras_desde_alineacion(tv, al))
            for i in indices[1:]:
                clips[i] = (np.zeros(0, np.float32), [])
            continue
        for i, (a, pal) in zip(indices, partes):
            _guardar_frase(frs[i], cfg, tono, a, pal)
            clips[i] = (a, pal)
    trozos, palabras, t = [], [], 0.0
    for a, pal in clips:
        palabras += [{"txt": w["txt"], "t0": round(w["t0"] + t, 3), "t1": round(w["t1"] + t, 3)} for w in pal]
        trozos.append(a)
        t += len(a) / SR
    return (np.concatenate(trozos) if trozos else np.zeros(SR, np.float32)), palabras


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


def sintetizar_escena(texto: str, cfg, carpeta: Path | None = None, emocion: float | None = None,
                      tono: str | None = None) -> tuple[np.ndarray, list[dict]]:
    """Devuelve (audio 24 kHz, palabras con tiempos relativos al inicio del audio)."""
    if cfg.motor == "estimar":
        dur = max(1.5, len(texto) / 15.0)
        return np.zeros(int(dur * SR), np.float32), _palabras(texto, 0.0, dur)
    if cfg.motor == "elevenlabs":
        return _elevenlabs(texto, cfg, tono)
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


class FaltaConfirmar(RuntimeError):
    """La narración gastaría créditos de ElevenLabs y no se confirmó el gasto."""


def generar(episodio: str, escenas, cfg, carpeta: Path, gastar: bool = False) -> list[dict]:
    """Por escena: {'wav', 'duracion', 'palabras'}. Reutiliza lo ya generado si el texto no cambió.
    Con ElevenLabs, si hay que pagar algo y gastar=False, se detiene y dice cuánto costaría."""
    carpeta = Path(carpeta) / episodio
    carpeta.mkdir(parents=True, exist_ok=True)
    if cfg.motor == "elevenlabs":
        costo = sum(creditos_voz(e.voz, cfg, e.tono) for e in escenas)
        if costo and not gastar:
            raise FaltaConfirmar(f"La voz gastaría ~{costo} créditos de ElevenLabs (lo demás ya está en la biblioteca). "
                                 "Para confirmar agrega --si; para un borrador gratis usa --voz kokoro.")
        if costo:
            print(f"  voz: ~{costo} créditos (solo las frases nuevas)")
        else:
            print("  voz: todo desde la biblioteca, 0 créditos")
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
                                         + ([cfg.modelo, cfg.estabilidad, cfg.estilo, esc.tono] if cfg.motor == "elevenlabs" else [])
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
        audio, palabras = sintetizar_escena(esc.voz, cfg, carpeta, emo, esc.tono)
        sf.write(wav, audio, SR)
        dur = len(audio) / SR
        meta.write_text(json.dumps({"huella": huella, "duracion": dur, "palabras": palabras}, ensure_ascii=False), encoding="utf-8")
        print(f"  voz {wav.name}: {dur:.1f} s")
        salida.append({"wav": wav, "duracion": dur, "palabras": palabras})
    return salida
