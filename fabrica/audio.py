"""Mezcla de audio: voz + efectos (sintetizados aquí, sin derechos de terceros) + música opcional."""
import subprocess

import numpy as np
import soundfile as sf

SR = 48000


def _remuestrear(x, sr):
    if sr == SR:
        return x
    n = int(len(x) * SR / sr)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def leer(ruta):
    x, sr = sf.read(str(ruta), dtype="float32", always_2d=True)
    return _remuestrear(x.mean(axis=1), sr)


def leer_con_ffmpeg(ruta):
    """Lee cualquier formato (mp3, m4a...) a mono 48 kHz."""
    crudo = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ruta), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                           capture_output=True, check=True).stdout
    return np.frombuffer(crudo, dtype=np.float32).copy()


def whoosh(dur=0.7, semilla=1):
    """Ruido filtrado con barrido de grave a agudo y vuelta: transición."""
    rng = np.random.default_rng(semilla)
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    ruido = rng.standard_normal(n).astype(np.float32)
    # filtro paso bajo de un polo con frecuencia variable
    corte = 300 + 3500 * np.sin(np.pi * t) ** 2
    a = np.exp(-2 * np.pi * corte / SR)
    y = np.empty(n, np.float32)
    acc = 0.0
    for i in range(n):
        acc = a[i] * acc + (1 - a[i]) * ruido[i]
        y[i] = acc
    env = np.sin(np.pi * t) ** 1.5
    y = y * env
    return (y / (np.abs(y).max() + 1e-9) * 0.5).astype(np.float32)


def pop(dur=0.12):
    """Golpe corto y tonal: aparece un texto."""
    t = np.arange(int(dur * SR)) / SR
    f = 900 * np.exp(-t * 18) + 250
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)
    return (y * 0.45).astype(np.float32)


def impacto(dur=0.9):
    """Golpe grave para momentos fuertes (guerra, pérdida)."""
    t = np.arange(int(dur * SR)) / SR
    f = 120 * np.exp(-t * 4) + 40
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5)
    rng = np.random.default_rng(3)
    y += rng.standard_normal(len(t)) * np.exp(-t * 30) * 0.3
    return (y / np.abs(y).max() * 0.7).astype(np.float32)


EFECTOS = {"whoosh": whoosh, "pop": pop, "impacto": impacto}


def _sumar(pista, clip, inicio, ganancia=1.0):
    i = int(inicio * SR)
    if i >= len(pista):
        return
    fin = min(len(pista), i + len(clip))
    pista[i:fin] += clip[: fin - i] * ganancia


def _ajustar(clip, n):
    """Repite (con fundido) o recorta un clip a n muestras."""
    if len(clip) >= n:
        return clip[:n].copy()
    f = min(len(clip) // 4, SR // 2)
    out = clip.copy()
    while len(out) < n:
        rampa = np.linspace(0, 1, f, dtype=np.float32)
        out[-f:] = out[-f:] * (1 - rampa) + clip[:f] * rampa
        out = np.concatenate([out, clip[f:]])
    return out[:n]


def mezclar(duracion, voces, efectos, musica=None, vol_musica=0.22, salida="mezcla.wav", ambientes=(), vol_ambiente=0.16):
    """voces: [(ruta, inicio)]; efectos: [(nombre interno o ruta de archivo, inicio, ganancia)];
    ambientes: [(ruta, t0, t1)] sonido de fondo por escena (con fundidos)."""
    n = int(duracion * SR)
    voz = np.zeros(n, np.float32)
    for ruta, inicio in voces:
        _sumar(voz, leer(ruta), inicio)
    pico = np.abs(voz).max()
    if pico > 0:
        voz *= 0.89 / pico  # normaliza la voz a ~-1 dBFS
    fx = np.zeros(n, np.float32)
    cache = {}
    for nombre, inicio, gan in efectos:
        if nombre not in cache:
            if nombre in EFECTOS:
                cache[nombre] = EFECTOS[nombre]()
            else:   # archivo (efecto generado y guardado en la biblioteca)
                c = leer_con_ffmpeg(nombre)
                cache[nombre] = c / (np.abs(c).max() + 1e-9) * 1.4   # los efectos a medida van al frente
        _sumar(fx, cache[nombre], inicio, gan)
    mezcla = voz + fx * 0.6
    for ruta, t0, t1 in ambientes:
        k = int((t1 - t0) * SR)
        c = leer_con_ffmpeg(ruta)
        c = _ajustar(c / (np.abs(c).max() + 1e-9), k)
        f = min(k // 3, int(0.6 * SR))
        env = np.ones(k, np.float32)
        env[:f] = np.linspace(0, 1, f)
        env[-f:] = np.linspace(1, 0, f)
        _sumar(mezcla, c * env, t0, vol_ambiente)
    if musica:
        tramos = [(musica, 0.0)] if isinstance(musica, (str, bytes)) else list(musica)
        m = np.zeros(n, np.float32)
        x = 2 * SR   # fundido cruzado de 2 s entre emociones
        for k, (ruta, t0) in enumerate(tramos):
            i0 = int(t0 * SR)
            i1 = int(tramos[k + 1][1] * SR) if k + 1 < len(tramos) else n
            c = _ajustar(leer_con_ffmpeg(ruta), min(n, i1 + x) - i0)
            c = c / (np.abs(c).max() + 1e-9)
            if k > 0:
                c[:x] *= np.linspace(0, 1, min(x, len(c)))[: len(c[:x])]
            if k + 1 < len(tramos):
                c[-x:] *= np.linspace(1, 0, min(x, len(c)))[-len(c[-x:]):]
            m[i0:i0 + len(c)] += c
        # "ducking": la música baja cuando hay voz
        env = np.convolve(np.abs(voz), np.ones(SR // 10) / (SR // 10), mode="same")
        activo = np.clip(env / (env.max() + 1e-9) * 8, 0, 1)
        suave = np.convolve(activo, np.ones(SR // 4) / (SR // 4), mode="same")
        env_fx = np.convolve(np.abs(fx), np.ones(SR // 10) / (SR // 10), mode="same")
        fx_activo = np.clip(env_fx / (env_fx.max() + 1e-9) * 6, 0, 1)
        ganancia = vol_musica * (1 - 0.6 * np.maximum(suave, 0.7 * fx_activo))   # también se aparta para los efectos
        t = np.arange(n) / SR
        ganancia *= np.clip(t / 1.0, 0, 1) * np.clip((duracion - t) / 2.0, 0, 1)  # entrada y salida suaves
        mezcla += m * ganancia
    mezcla = np.clip(mezcla, -1, 1)
    sf.write(salida, np.stack([mezcla, mezcla], axis=1), SR)
    return salida
