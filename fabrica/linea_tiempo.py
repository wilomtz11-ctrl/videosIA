"""Compila el episodio (guion + duración de la voz) a la escena que dibuja el motor 3D.

Toda la lógica de tiempos vive aquí (Python, con tests); el motor JavaScript solo interpola.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .lugares import Lugares
from .modelo import ALTURAS, Episodio

ENTRADA_VOZ = 0.12       # la voz empieza un instante después del corte
DERIVA = 0.05            # acercamiento lento dentro de cada escena (5 %)
TRANSICION_MAPA = 1.2
TAM = {"pais": 58, "ciudad": 34, "agua": 34, "propio": 34}
ESTILO = {"pais": "pais", "ciudad": "punto", "agua": "agua", "propio": "punto"}


def _dist_angular(a, b):
    (lo1, la1), (lo2, la2) = a, b
    f1, f2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    c = math.sin(f1) * math.sin(f2) + math.cos(f1) * math.cos(f2) * math.cos(dl)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _norm(w: str) -> str:
    import unicodedata
    w = unicodedata.normalize("NFKD", w.lower()).encode("ascii", "ignore").decode()
    return "".join(c for c in w if c.isalnum())


def buscar_frase(palabras: list[dict], frase: str) -> float | None:
    """Momento en que empieza a decirse 'frase' (tiempo de su primera palabra)."""
    obj = [_norm(x) for x in frase.split() if _norm(x)]
    dichas = [_norm(p["txt"]) for p in palabras]
    for i in range(len(dichas) - len(obj) + 1):
        if dichas[i:i + len(obj)] == obj:
            return palabras[i]["t0"]
    return None


def agrupar_subtitulos(palabras, max_palabras=3, max_letras=18):
    grupos, actual = [], []
    for i, p in enumerate(palabras):
        actual.append(p)
        largo = sum(len(x["txt"]) + 1 for x in actual)
        if len(actual) >= max_palabras or largo >= max_letras or p["txt"][-1] in ".,;:?!…" or i == len(palabras) - 1:
            grupos.append({"t0": actual[0]["t0"], "t1": actual[-1]["t1"], "palabras": actual})
            actual = []
    for a, b in zip(grupos, grupos[1:]):          # sin huecos entre grupos
        if b["t0"] - a["t1"] < 0.6:
            a["t1"] = b["t0"]
    return grupos


@dataclass
class Compilado:
    escena: dict                       # lo que lee el motor (escena.json)
    voces: list = field(default_factory=list)      # [(wav, inicio)]
    efectos: list = field(default_factory=list)    # [(nombre interno o EfectoIA, inicio, ganancia)]
    ambientes: list = field(default_factory=list)  # [(pedido, t0, t1)]
    musicas: list = field(default_factory=list)    # [(emoción o pedido, inicio)] cambios de música
    tiempos: list = field(default_factory=list)    # [(id, t0, t1)]


def compilar(ep: Episodio, voces: list[dict], lugares: Lugares, info_capas: dict, ancho_alto) -> Compilado:
    out = Compilado(escena={})
    cam_kf, mapas_pistas, formas_ev, anios, golpes, pulsos = [], [], [], [], [], []
    titulares, etiquetas, anillos, flechas, subtitulos = [], [], [], [], []
    t = 0.0
    cam_prev = None          # (lon, lat, alt, incl, rumbo) al final de la escena anterior
    mapa_prev = None
    pintadas = set()
    for i, (esc, v) in enumerate(zip(ep.escenas, voces)):
        t0 = t
        t1 = t0 + ENTRADA_VOZ + v["duracion"] + esc.pausa
        out.tiempos.append((esc.id, t0, t1))
        out.voces.append((v["wav"], t0 + ENTRADA_VOZ))
        abs_pal = [{**p, "t0": p["t0"] + t0 + ENTRADA_VOZ, "t1": p["t1"] + t0 + ENTRADA_VOZ} for p in v["palabras"]]
        for g in agrupar_subtitulos(abs_pal):
            subtitulos.append(g)
        # ritmo: un empujón de cámara al empezar cada frase (cambio visual cada pocos segundos)
        for k, p in enumerate(abs_pal):
            if k == 0 or abs_pal[k - 1]["txt"][-1] in ".?!…":
                pulsos.append(round(p["t0"], 3))
        for frase in esc.golpes:
            tg = buscar_frase(abs_pal, frase)
            if tg is None:
                raise ValueError(f"escena '{esc.id}': el golpe '{frase}' no aparece tal cual en la narración")
            golpes.append({"t": round(tg, 3), "texto": frase.upper() if len(frase) < 22 else frase})
            out.efectos.append(("impacto", max(0, tg - 0.05), 0.55))

        # --- cámara ---
        if esc.camara:
            c = esc.camara
            lon, lat = lugares.punto(c.ir_a)
            destino = (lon, lat, c.altura, c.inclinacion, c.rumbo)
            if cam_prev is None:
                # el video arranca en el espacio y cae hacia el primer objetivo: gancho visual inmediato
                inicio = (lon + 25, lat + 12, ALTURAS["espacio"], 0, 0)
                cam_kf.append([t0, *inicio])
                mov = min(t1 - t0, max(2.5, c.duracion_movimiento))
            else:
                cam_kf.append([t0, *cam_prev])
                mov = min(c.duracion_movimiento, (t1 - t0) * 0.7)
                lejos = _dist_angular(cam_prev[:2], destino[:2]) > 1 or abs(math.log(cam_prev[2] / destino[2])) > 0.3
                if lejos:
                    out.efectos.append(("whoosh", max(0, t0 - 0.25), 0.7))
            cam_kf.append([t0 + mov, *destino])
            fin = (destino[0], destino[1], destino[2] * (1 - DERIVA), destino[3], destino[4])
        else:
            fin = (cam_prev[0], cam_prev[1], cam_prev[2] * (1 - DERIVA), cam_prev[3], cam_prev[4])
        cam_kf.append([t1, *fin])
        cam_prev = fin

        # --- mapa político ---
        mapa = esc.mapa or mapa_prev
        if mapa != mapa_prev:
            mapas_pistas.append([t0, mapa])
            for f in sorted(pintadas):        # al cambiar de mapa se borra lo pintado
                formas_ev.append({"forma": f, "tipo": "despintar", "t": t0, "dur": TRANSICION_MAPA})
            pintadas.clear()
        mapa_prev = mapa

        # --- formas ---
        for r in esc.resaltar:
            formas_ev.append({"forma": r.forma, "tipo": "resaltar", "t0": t0 + r.retraso, "t1": t1, "color": r.color})
        for p in esc.pintar:
            formas_ev.append({"forma": p.forma, "tipo": "pintar", "t": t0 + p.retraso, "dur": p.duracion, "color": p.color})
            pintadas.add(p.forma)

        # las etiquetas nuevas aparecen cuando la cámara ya casi llegó
        t_etq = t0 + 0.75 * mov if esc.camara else t0

        # --- año, titular, etiquetas, anillos, flechas ---
        if esc.anio is not None:
            anios.append([t0, esc.anio])
        if esc.titular:
            titulares.append({"t0": t0 + (0 if i == 0 else esc.titular.retraso), "t1": t1,
                              "texto": esc.titular.texto, "estilo": esc.titular.estilo})
            out.efectos.append(("pop", t0 + esc.titular.retraso, 0.8))
        for e in esc.etiquetas:
            if e.en is None:
                raise ValueError(f"escena '{esc.id}': una etiqueta necesita 'en'")
            if isinstance(e.en, str):
                lug = lugares.buscar(e.en)
                tipo, nombre, (lon, lat) = lug.tipo, lug.nombre, (lug.lon, lug.lat)
            else:
                tipo, nombre, (lon, lat) = "propio", e.texto or "", e.en
            texto = e.texto or (nombre.upper() if tipo == "pais" else nombre)
            etiquetas.append({"t0": t_etq, "t1": t1, "texto": texto, "lon": lon, "lat": lat,
                              "tam": e.tam or TAM[tipo], "estilo": e.estilo or ESTILO[tipo]})
        for a in esc.anillos:
            lon, lat = lugares.punto(a.en)
            anillos.append({"t0": t0 + a.retraso, "t1": t1, "lon": lon, "lat": lat, "color": a.color})
        for f in esc.flechas:
            flechas.append({"t0": t0 + f.retraso, "t1": t1, "dur": f.duracion, "de": lugares.punto(f.de),
                            "a": lugares.punto(f.a), "color": f.color})
            out.efectos.append(("whoosh", t0 + f.retraso, 0.45))
        for ef in esc.efectos:
            if isinstance(ef, str):
                out.efectos.append((ef, t0 + 0.1, 1.0))
            else:
                out.efectos.append((ef, t0 + ef.retraso, ef.vol))
        if esc.ambiente:
            out.ambientes.append((esc.ambiente, t0, t1))
        if esc.musica:
            out.musicas.append((esc.musica, t0))
        t = t1

    # etiquetas idénticas en escenas seguidas = un solo intervalo (sin parpadeo)
    unidas = []
    for e in etiquetas:
        prev = next((u for u in reversed(unidas) if (u["texto"], u["lon"], u["lat"]) == (e["texto"], e["lon"], e["lat"])), None)
        if prev and abs(prev["t1"] - e["t0"]) < 1e-6:
            prev["t1"] = e["t1"]
        else:
            unidas.append(dict(e))
    # titulares iguales seguidos también se unen
    tit = []
    for x in titulares:
        if tit and tit[-1]["texto"] == x["texto"] and abs(tit[-1]["t1"] - x["t0"]) < 0.5:
            tit[-1]["t1"] = x["t1"]
        else:
            tit.append(x)

    out.escena = {
        "formato": {"ancho": ancho_alto[0], "alto": ancho_alto[1]},
        "duracion": round(t, 3),
        "region": list(ep.region),
        "exageracion": ep.exageracion,
        **info_capas,
        "camara": [[round(x, 4) for x in k] for k in cam_kf],
        "mapas_pistas": mapas_pistas,
        "transicion_mapa": TRANSICION_MAPA,
        "formas_eventos": formas_ev,
        "anios": anios,
        "titulares": tit,
        "etiquetas": unidas,
        "anillos": anillos,
        "flechas": flechas,
        "subtitulos": subtitulos,
        "golpes": golpes,
        "pulsos": pulsos,
    }
    return out
