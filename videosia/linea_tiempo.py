"""Línea de tiempo: convierte las escenas del episodio + duración de cada voz en el estado de cada instante."""
import math
import re

from .render import rampa

ENTRADA_VOZ = 0.15     # segundos entre el inicio de la escena y el inicio de la voz
PAUSA = 0.35           # silencio al final de cada escena
DUR_MIN = 2.0
DERIVA = 0.04          # acercamiento lento dentro de cada escena (4 %)


def _camara(defin, previa):
    if not defin:
        return previa
    return (defin["centro"][0], defin["centro"][1], defin["alto"])


def _interp_cam(a, b, m):
    return (a[0] + (b[0] - a[0]) * m, a[1] + (b[1] - a[1]) * m,
            math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * m))


def _subtitulos(texto, ini, fin):
    """Reparte las palabras en el tiempo según su largo; agrupa de a 3 (o menos si hay puntuación)."""
    palabras = [p for p in re.split(r"\s+", texto.strip()) if p]
    if not palabras:
        return []
    pesos = []
    for p in palabras:
        w = len(p) + 1.5
        if p[-1] in ",;:":
            w += 4
        elif p[-1] in ".?!…":
            w += 7
        pesos.append(w)
    total = sum(pesos)
    t = ini
    tiempos = []
    for p, w in zip(palabras, pesos):
        d = (fin - ini) * w / total
        tiempos.append({"txt": p, "ini": t, "fin": t + d})
        t += d
    grupos, actual, largo = [], [], 0
    for i, w in enumerate(tiempos):
        actual.append(w)
        largo += len(w["txt"]) + 1
        if len(actual) >= 3 or largo >= 17 or w["txt"][-1] in ".,;:?!…" or i == len(tiempos) - 1:
            grupos.append({"palabras": actual, "ini": actual[0]["ini"], "fin": actual[-1]["fin"]})
            actual, largo = [], 0
    for a, b in zip(grupos, grupos[1:]):
        a["fin"] = b["ini"]
    grupos[-1]["fin"] += 0.3
    return grupos


class LineaTiempo:
    def __init__(self, ep, duraciones_voz):
        self.ep = ep
        self.escenas = []
        t = 0.0
        cam_prev = None
        prev = None
        self.voces, self.efectos, self.subtitulos = [], [], []
        grupos = ep.get("grupos_etiquetas", {})
        for esc, (ruta, dvoz) in zip(ep["escenas"], duraciones_voz):
            esc = dict(esc, etiquetas=[x for item in esc.get("etiquetas", [])
                                       for x in (grupos[item[1:]] if isinstance(item, str) else [item])])
            dur = max(DUR_MIN, ENTRADA_VOZ + dvoz + esc.get("pausa", PAUSA))
            e = dict(esc)
            e["t0"], e["t1"] = t, t + dur
            fin_cam = _camara(esc.get("camara"), cam_prev)
            e["cam_fin"] = fin_cam
            e["cam_ini"] = cam_prev or fin_cam
            e["mov"] = esc.get("camara", {}).get("mov", 1.4) if esc.get("camara") else 0
            # mapa y pinturas
            pint = [dict(p, t=t + p.get("retraso", 0.5)) for p in esc.get("pintar", [])]
            if prev and prev["mapa"] == esc["mapa"]:
                e["pinturas"] = prev["pinturas"] + pint
                e["anterior"] = None
            else:
                e["pinturas"] = pint
                e["anterior"] = {"mapa": prev["mapa"], "pinturas": prev["pinturas"]} if prev else None
            e["transicion"] = esc.get("transicion", 1.2)
            for clave in ("destacar", "anillos", "flechas"):
                e[clave] = [dict(x, t=t + x.get("retraso", 0.3), t_fin=t + x["hasta"] if "hasta" in x else t + dur)
                            for x in esc.get(clave, [])]
            self.voces.append((ruta, t + ENTRADA_VOZ))
            self.subtitulos += _subtitulos(esc["narracion"], t + ENTRADA_VOZ, t + ENTRADA_VOZ + dvoz)
            # efectos automáticos
            cambia_mapa = prev is not None and prev["mapa"] != esc["mapa"]
            mueve = prev is not None and fin_cam != prev["cam_fin"]
            if cambia_mapa or mueve:
                self.efectos.append(("whoosh", max(0, t - 0.25), 0.8 if cambia_mapa else 0.5))
            if esc.get("texto"):
                self.efectos.append(("pop", t + _texto(esc)["retraso"], 0.9))
            for f in e["flechas"]:
                self.efectos.append(("whoosh", f["t"], 0.45))
            for nombre in esc.get("efectos", []):
                self.efectos.append((nombre, t + 0.1, 1.0))
            self.escenas.append(e)
            prev = e
            # la cámara final incluye la deriva, para que la siguiente escena arranque sin salto
            cam_prev = (fin_cam[0], fin_cam[1], fin_cam[2] * (1 - DERIVA))
            t += dur
        self.duracion = t
        for s in self.subtitulos:
            s["fin"] = min(s["fin"], self.duracion)

    def _indice(self, t):
        for i, e in enumerate(self.escenas):
            if t < e["t1"]:
                return i
        return len(self.escenas) - 1

    def estado(self, t):
        i = self._indice(t)
        e = self.escenas[i]
        ant = self.escenas[i - 1] if i > 0 else None
        sig = self.escenas[i + 1] if i + 1 < len(self.escenas) else None
        # cámara
        m = rampa(t, e["t0"], e["mov"]) if e["mov"] else 1.0
        cam = _interp_cam(e["cam_ini"], e["cam_fin"], m)
        prog = (t - e["t0"]) / (e["t1"] - e["t0"])
        cam = (cam[0], cam[1], cam[2] * (1 - DERIVA * prog))
        # año (cuenta animada entre años numéricos)
        anio = e.get("anio")
        escala = 1.0
        if ant is not None and ant.get("anio") != anio:
            a0, a1 = ant.get("anio"), anio
            k = rampa(t, e["t0"], 0.9)
            if isinstance(a0, int) and isinstance(a1, int):
                anio = round(a0 + (a1 - a0) * k)
            escala = 1 + 0.12 * math.sin(math.pi * min(1, max(0, (t - e["t0"]) / 0.9)))
        # etiquetas con fundido solo si no estaban / no seguirán
        def clave(x):
            return (x["texto"], x["lon"], x["lat"])
        prev_k = {clave(x) for x in (ant or {}).get("etiquetas", [])}
        sig_k = {clave(x) for x in (sig or {}).get("etiquetas", [])}
        etiquetas = []
        for x in e.get("etiquetas", []):
            a = 1.0
            if clave(x) not in prev_k:
                a *= rampa(t, e["t0"] + x.get("retraso", 0.25), 0.4)
            if clave(x) not in sig_k:
                a *= 1 - rampa(t, e["t1"] - 0.35, 0.35)
            etiquetas.append((x, a))
        titular = None
        if e.get("texto"):
            tx = _texto(e)
            ini = e["t0"] + tx["retraso"]
            fin = e["t0"] + tx["hasta"] if tx.get("hasta") else e["t1"]
            alfa = rampa(t, ini, 0.2) * (1 - rampa(t, fin - 0.25, 0.25))
            if alfa > 0:
                k = min(1, max(0, (t - ini) / 0.35))
                rebote = 1 + 0.08 * math.sin(math.pi * k) * (1 - k)  # pequeño "pop" con rebote
                titular = dict(tx, alfa=alfa, escala=(0.85 + 0.15 * suave_back(k)) * rebote)
        return {
            "t": t, "camara": cam, "mapa": e["mapa"], "pinturas": e["pinturas"],
            "anterior": e["anterior"], "fundido": rampa(t, e["t0"], e["transicion"]) if e["anterior"] else 1,
            "anio": anio, "anio_escala": escala, "etiquetas": etiquetas,
            "destacar": e["destacar"], "anillos": e["anillos"], "flechas": e["flechas"],
            "titular": titular, "subtitulos": self.subtitulos,
        }


def suave_back(k):
    """Entrada con un leve sobrepaso (efecto rebote)."""
    c = 1.7
    k -= 1
    return 1 + (c + 1) * k ** 3 + c * k ** 2


def _texto(esc):
    tx = esc["texto"]
    if isinstance(tx, str):
        tx = {"texto": tx}
    return {"estilo": "nota", "retraso": 0.1, **tx}
