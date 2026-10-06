"""Dibuja cada fotograma del video con Skia (vectores con suavizado).

Coordenadas: proyección equirectangular con corrección de coseno de la latitud
central de la región. Los caminos se arman una vez en "coordenadas mundo" y la
cámara (centro + alto visible en grados) se aplica como transformación.
"""
import math
import re
from pathlib import Path

import numpy as np
import skia

from . import geo

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "fuentes"

FORMATOS = {
    # ancho, alto, factor de zoom respecto al vertical, posiciones (fracción del alto)
    "vertical": dict(W=1080, H=1920, k_alto=1.0, y_anio=0.105, y_titular=0.205, y_subs=0.70, y_credito=0.035),
    "horizontal": dict(W=1920, H=1080, k_alto=0.85, y_anio=0.11, y_titular=0.27, y_subs=0.86, y_credito=0.04),
}


# ---------- utilidades ----------

def color(hexa, alfa=1.0):
    hexa = hexa.lstrip("#")
    r, g, b = int(hexa[0:2], 16), int(hexa[2:4], 16), int(hexa[4:6], 16)
    return skia.Color(r, g, b, max(0, min(255, int(round(alfa * 255)))))


def mezclar_color(a, b, t):
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{int(round(x + (y - x) * t)):02x}" for x, y in zip(ca, cb))


def suave(x):
    """Curva de aceleración/desaceleración (0..1 -> 0..1)."""
    x = max(0.0, min(1.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def rampa(t, inicio, dur):
    return suave((t - inicio) / dur) if dur > 0 else float(t >= inicio)


def fuente(peso="ExtraBold"):
    return skia.Typeface.MakeFromFile(str(FUENTES / f"Montserrat-{peso}.ttf"))


# ---------- motor ----------

class Escenario:
    def __init__(self, ep, formato="vertical"):
        self.ep = ep
        f = FORMATOS[formato]
        self.W, self.H = f["W"], f["H"]
        self.lay = f
        self.u = min(self.W, self.H) / 1080  # unidad de tamaño de texto
        self.region = ep["region"]
        lat_c = (self.region[1] + self.region[3]) / 2
        self.c = math.cos(math.radians(lat_c))
        self.tf = {p: fuente(p) for p in ("ExtraBold", "Bold", "SemiBold")}
        est = ep.get("estilo", {})
        self.oceano = est.get("oceano", "#0E2233")
        self.borde = est.get("borde", "#13222E")
        self.tierra = est.get("tierra", "#C9C2B2")
        self.colores = ep.get("colores", {})
        self.mapas = {k: self._armar_mapa(v) for k, v in ep["mapas"].items()}
        self.formas = {k: self._camino(geo.forma_derivada(v, self.region)) for k, v in ep.get("formas", {}).items()}
        self.reticula = self._reticula()
        self.superficie = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(self.W, self.H, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType))
        # capas fijas de pantalla: se dibujan una sola vez (los degradados son caros)
        self.img_fondo = self._capa_fija(self._fondo)
        self.img_vineta = self._capa_fija(self._vineta)

    def _capa_fija(self, dibujar):
        sup = skia.Surface(self.W, self.H)
        c = sup.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        dibujar(c)
        return sup.makeImageSnapshot()

    # --- geometría a caminos ---
    def _camino(self, g):
        p = skia.Path()
        p.setFillType(skia.PathFillType.kEvenOdd)
        for poli in geo.poligonos(g):
            for anillo in [poli.exterior, *poli.interiors]:
                pts = list(anillo.coords)
                p.moveTo(pts[0][0] * self.c, -pts[0][1])
                for q in pts[1:]:
                    p.lineTo(q[0] * self.c, -q[1])
                p.close()
        return p

    def _armar_mapa(self, defin):
        paises = geo.cargar(defin["anio"], self.region)
        cambios = defin.get("colores", {})
        capas = []
        union = skia.Path()
        for nombre, g in paises.items():
            camino = self._camino(g)
            col = cambios.get(nombre) or self.colores.get(nombre) or self.tierra
            capas.append((nombre, camino, col))
            union.addPath(camino)
        return {"capas": capas, "union": union}

    def _reticula(self):
        p = skia.Path()
        x0, y0, x1, y1 = self.region
        for lon in range(int(x0 // 5 * 5), int(x1) + 1, 5):
            p.moveTo(lon * self.c, -y0)
            p.lineTo(lon * self.c, -y1)
        for lat in range(int(y0 // 5 * 5), int(y1) + 1, 5):
            p.moveTo(x0 * self.c, -lat)
            p.lineTo(x1 * self.c, -lat)
        return p

    # --- cámara ---
    def escala(self, alto):
        return self.H / (alto * self.lay["k_alto"])

    def a_pantalla(self, cam, lon, lat):
        s = self.escala(cam[2])
        return (self.W / 2 + s * (lon - cam[0]) * self.c, self.H / 2 - s * (lat - cam[1]))

    def _aplicar_camara(self, canvas, cam):
        s = self.escala(cam[2])
        canvas.translate(self.W / 2, self.H / 2)
        canvas.scale(s, s)
        canvas.translate(-cam[0] * self.c, cam[1])
        return s

    # --- capas de dibujo ---
    def _fondo(self, canvas):
        r = max(self.W, self.H) * 0.75
        sh = skia.GradientShader.MakeRadial(skia.Point(self.W / 2, self.H * 0.45), r,
                                             [color("#16405C"), color(self.oceano), color("#060F17")], [0, 0.6, 1])
        canvas.drawPaint(skia.Paint(Shader=sh))

    def _vineta(self, canvas):
        r = max(self.W, self.H) * 0.8
        canvas.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial(
            skia.Point(self.W / 2, self.H / 2), r, [color("#000000", 0), color("#000000", 0.45)], [0.55, 1])))
        canvas.drawRect(skia.Rect.MakeWH(self.W, self.H * 0.3), skia.Paint(Shader=skia.GradientShader.MakeLinear(
            [skia.Point(0, 0), skia.Point(0, self.H * 0.3)], [color("#000000", 0.6), color("#000000", 0)])))

    def _dibujar_estado(self, canvas, cam, mapa, pinturas, t):
        """Mapa base + zonas repintadas (estado persistente)."""
        canvas.save()
        s = self._aplicar_camara(canvas, cam)
        canvas.drawPath(self.reticula, skia.Paint(Color=color("#FFFFFF", 0.05), Style=skia.Paint.kStroke_Style,
                                                  StrokeWidth=1.2 / s, AntiAlias=True))
        m = self.mapas[mapa]
        sombra = skia.Paint(Color=color("#000000", 0.45), AntiAlias=True,
                            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14, False))
        canvas.save()
        canvas.translate(4 / s, 6 / s)
        canvas.drawPath(m["union"], sombra)
        canvas.restore()
        relleno = skia.Paint(AntiAlias=True)
        trazo = skia.Paint(Color=color(self.borde), Style=skia.Paint.kStroke_Style, StrokeWidth=2.2 / s,
                           AntiAlias=True, StrokeJoin=skia.Paint.kRound_Join)
        for _, camino, col in m["capas"]:
            relleno.setColor(color(col))
            canvas.drawPath(camino, relleno)
        for p in pinturas:
            a = rampa(t, p["t"], p.get("dur", 1.4))
            if a <= 0:
                continue
            relleno.setColor(color(p["color"], a))
            canvas.drawPath(self.formas[p["forma"]], relleno)
        for _, camino, _ in m["capas"]:
            canvas.drawPath(camino, trazo)
        canvas.restore()

    def _destacar(self, canvas, cam, d, t):
        a = rampa(t, d["t"], 0.5) * (1 - rampa(t, d["t_fin"] - 0.35, 0.35))
        if a <= 0:
            return
        canvas.save()
        s = self._aplicar_camara(canvas, cam)
        pulso = 0.5 + 0.5 * math.sin((t - d["t"]) * 2 * math.pi * 0.9)
        camino = self.formas[d["forma"]]
        col = d.get("color", "#4CC9F0")
        brillo = skia.Paint(Color=color(col, 0.9 * a), Style=skia.Paint.kStroke_Style, StrokeWidth=14 / s,
                            AntiAlias=True, StrokeJoin=skia.Paint.kRound_Join,
                            MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10, False))
        canvas.drawPath(camino, brillo)
        canvas.drawPath(camino, skia.Paint(Color=color(col, (0.25 + 0.35 * pulso) * a), AntiAlias=True))
        canvas.drawPath(camino, skia.Paint(Color=color("#FFFFFF", 0.9 * a), Style=skia.Paint.kStroke_Style,
                                           StrokeWidth=3.5 / s, AntiAlias=True, StrokeJoin=skia.Paint.kRound_Join))
        canvas.restore()

    def _texto_centrado(self, canvas, txt, x, y, tam, col, peso="ExtraBold", alfa=1.0, trazo=0, col_trazo="#0B1620",
                        rot=0, escala=1.0):
        font = skia.Font(self.tf[peso], tam * self.u * escala)
        lineas = txt.split("\n")
        met = font.getMetrics()
        alto_linea = (met.fDescent - met.fAscent) * 1.02
        canvas.save()
        canvas.translate(x, y)
        if rot:
            canvas.rotate(-rot)
        y0 = -alto_linea * (len(lineas) - 1) / 2
        for i, linea in enumerate(lineas):
            w = font.measureText(linea)
            base = y0 + i * alto_linea - (met.fAscent + met.fDescent) / 2
            if trazo:
                canvas.drawString(linea, -w / 2, base, font,
                                  skia.Paint(Color=color(col_trazo, alfa), Style=skia.Paint.kStroke_Style,
                                             StrokeWidth=trazo * self.u * escala, AntiAlias=True,
                                             StrokeJoin=skia.Paint.kRound_Join))
            canvas.drawString(linea, -w / 2, base, font, skia.Paint(Color=color(col, alfa), AntiAlias=True))
        canvas.restore()

    def _etiqueta(self, canvas, cam, e, alfa):
        x, y = self.a_pantalla(cam, e["lon"], e["lat"])
        tam = e.get("tam", 40)
        estilo = e.get("estilo", "pais")
        if estilo == "punto":
            r = 9 * self.u
            canvas.drawCircle(x, y, r + 4 * self.u, skia.Paint(Color=color("#0B1620", alfa), AntiAlias=True))
            canvas.drawCircle(x, y, r, skia.Paint(Color=color("#FFFFFF", alfa), AntiAlias=True))
            font = skia.Font(self.tf["ExtraBold"], tam * self.u)
            lado = e.get("lado", "der")
            w = font.measureText(e["texto"])
            dx = (r + 14 * self.u + w / 2) * (1 if lado == "der" else -1)
            self._texto_centrado(canvas, e["texto"], x + dx, y, tam, "#FFFFFF", alfa=alfa, trazo=9)
        elif estilo == "claro":
            self._texto_centrado(canvas, e["texto"], x, y, tam, "#FFFFFF", alfa=alfa, trazo=9, rot=e.get("rot", 0))
        else:
            self._texto_centrado(canvas, e["texto"], x, y, tam, e.get("color", "#14212B"), alfa=alfa,
                                 rot=e.get("rot", 0), trazo=e.get("trazo", 0), col_trazo=e.get("col_trazo", "#FFFFFF"))

    def _anillo(self, canvas, cam, a, t):
        alfa = rampa(t, a["t"], 0.4) * (1 - rampa(t, a["t_fin"] - 0.3, 0.3))
        if alfa <= 0:
            return
        x, y = self.a_pantalla(cam, a["lon"], a["lat"])
        r = a.get("radio", 70) * self.u * (1 + 0.12 * math.sin((t - a["t"]) * 6))
        col = a.get("color", "#FFD166")
        canvas.drawCircle(x, y, r, skia.Paint(Color=color(col, 0.6 * alfa), Style=skia.Paint.kStroke_Style,
                                              StrokeWidth=16 * self.u, AntiAlias=True,
                                              MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 8, False)))
        canvas.drawCircle(x, y, r, skia.Paint(Color=color(col, alfa), Style=skia.Paint.kStroke_Style,
                                              StrokeWidth=7 * self.u, AntiAlias=True))

    def _flecha(self, canvas, cam, f, t):
        prog = rampa(t, f["t"], f.get("dur", 1.1))
        alfa = 1 - rampa(t, f["t_fin"] - 0.3, 0.3)
        if prog <= 0 or alfa <= 0:
            return
        x0, y0 = self.a_pantalla(cam, *f["de"])
        x1, y1 = self.a_pantalla(cam, *f["a"])
        dx, dy = x1 - x0, y1 - y0
        curva = f.get("curva", 0.25)
        cx, cy = (x0 + x1) / 2 - dy * curva, (y0 + y1) / 2 + dx * curva
        n = 40
        pts = []
        for i in range(int(n * prog) + 1):
            s = i / n
            pts.append(((1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s * s * x1,
                        (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s * s * y1))
        if len(pts) < 2:
            return
        p = skia.Path()
        p.moveTo(*pts[0])
        for q in pts[1:]:
            p.lineTo(*q)
        col = f.get("color", "#FF4D4F")
        ancho = 12 * self.u
        canvas.drawPath(p, skia.Paint(Color=color("#000000", 0.5 * alfa), Style=skia.Paint.kStroke_Style,
                                      StrokeWidth=ancho + 8 * self.u, AntiAlias=True, StrokeCap=skia.Paint.kRound_Cap))
        canvas.drawPath(p, skia.Paint(Color=color(col, alfa), Style=skia.Paint.kStroke_Style, StrokeWidth=ancho,
                                      AntiAlias=True, StrokeCap=skia.Paint.kRound_Cap))
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        ang = math.atan2(by - ay, bx - ax)
        L = 42 * self.u
        punta = skia.Path()
        punta.moveTo(bx + math.cos(ang) * L * 0.5, by + math.sin(ang) * L * 0.5)
        punta.lineTo(bx + math.cos(ang + 2.5) * L, by + math.sin(ang + 2.5) * L)
        punta.lineTo(bx + math.cos(ang - 2.5) * L, by + math.sin(ang - 2.5) * L)
        punta.close()
        canvas.drawPath(punta, skia.Paint(Color=color(col, alfa), AntiAlias=True))

    def _caja_texto(self, canvas, txt, cx, cy, tam, col_txt, col_caja, alfa, escala):
        font = skia.Font(self.tf["ExtraBold"], tam * self.u * escala)
        lineas = txt.split("\n")
        met = font.getMetrics()
        alto_linea = (met.fDescent - met.fAscent) * 1.05
        ancho = max(font.measureText(l) for l in lineas)
        pad = 26 * self.u * escala
        alto = alto_linea * len(lineas)
        rect = skia.Rect.MakeXYWH(cx - ancho / 2 - pad, cy - alto / 2 - pad * 0.8, ancho + 2 * pad, alto + 1.6 * pad)
        canvas.drawRRect(skia.RRect.MakeRectXY(rect.makeOffset(0, 8 * self.u), 22 * self.u, 22 * self.u),
                         skia.Paint(Color=color("#000000", 0.35 * alfa), AntiAlias=True,
                                    MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10, False)))
        canvas.drawRRect(skia.RRect.MakeRectXY(rect, 22 * self.u, 22 * self.u),
                         skia.Paint(Color=color(col_caja, alfa), AntiAlias=True))
        for i, l in enumerate(lineas):
            w = font.measureText(l)
            base = cy - alto / 2 + i * alto_linea - met.fAscent + (alto_linea - (met.fDescent - met.fAscent)) / 2
            canvas.drawString(l, cx - w / 2, base, font, skia.Paint(Color=color(col_txt, alfa), AntiAlias=True))

    def _subtitulos(self, canvas, sub, t):
        """Subtítulos estilo karaoke: grupo de palabras con la palabra actual resaltada."""
        if not sub:
            return
        grupo = None
        for g in sub:
            if g["ini"] <= t < g["fin"]:
                grupo = g
                break
        if grupo is None:
            return
        tam = 70 * self.u
        font = skia.Font(self.tf["ExtraBold"], tam)
        espacio = font.measureText(" ")
        anchos = [font.measureText(p["txt"]) for p in grupo["palabras"]]
        total = sum(anchos) + espacio * (len(anchos) - 1)
        if total > self.W * 0.88:  # achica la letra si el grupo no cabe
            tam *= self.W * 0.88 / total
            font = skia.Font(self.tf["ExtraBold"], tam)
            espacio = font.measureText(" ")
            anchos = [font.measureText(p["txt"]) for p in grupo["palabras"]]
            total = sum(anchos) + espacio * (len(anchos) - 1)
        x = self.W / 2 - total / 2
        y = self.H * self.lay["y_subs"]
        met = font.getMetrics()
        base = y - (met.fAscent + met.fDescent) / 2
        entrada = rampa(t, grupo["ini"], 0.12)
        esc = 0.9 + 0.1 * entrada
        canvas.save()
        canvas.translate(self.W / 2, y)
        canvas.scale(esc, esc)
        canvas.translate(-self.W / 2, -y)
        for p, w in zip(grupo["palabras"], anchos):
            activa = p["ini"] <= t < p["fin"] or (p is grupo["palabras"][-1] and t >= p["ini"])
            canvas.drawString(p["txt"], x, base, font, skia.Paint(Color=color("#000000", 0.95), Style=skia.Paint.kStroke_Style,
                                                                   StrokeWidth=14 * self.u, AntiAlias=True,
                                                                   StrokeJoin=skia.Paint.kRound_Join))
            canvas.drawString(p["txt"], x, base, font,
                              skia.Paint(Color=color("#FFD166" if activa else "#FFFFFF"), AntiAlias=True))
            x += w + espacio
        canvas.restore()

    # --- fotograma completo ---
    def fotograma(self, estado):
        """estado: diccionario calculado por la línea de tiempo (ver linea_tiempo.py)."""
        canvas = self.superficie.getCanvas()
        t = estado["t"]
        cam = estado["camara"]
        canvas.drawImage(self.img_fondo, 0, 0)
        # mapa con fundido entre estados
        if estado.get("anterior") and estado["fundido"] < 1:
            ant = estado["anterior"]
            self._dibujar_estado(canvas, cam, ant["mapa"], ant["pinturas"], t)
            canvas.saveLayerAlpha(None, int(255 * estado["fundido"]))
            self._dibujar_estado(canvas, cam, estado["mapa"], estado["pinturas"], t)
            canvas.restore()
        else:
            self._dibujar_estado(canvas, cam, estado["mapa"], estado["pinturas"], t)
        for d in estado["destacar"]:
            self._destacar(canvas, cam, d, t)
        for e, alfa in estado["etiquetas"]:
            if alfa > 0:
                self._etiqueta(canvas, cam, e, alfa)
        for a in estado["anillos"]:
            self._anillo(canvas, cam, a, t)
        for f in estado["flechas"]:
            self._flecha(canvas, cam, f, t)
        # viñeta y degradado superior para que se lea la interfaz
        canvas.drawImage(self.img_vineta, 0, 0)
        # año
        anio = estado["anio"]
        if anio is not None:
            self._texto_centrado(canvas, str(anio), self.W / 2, self.H * self.lay["y_anio"], 150, "#FFD166",
                                 trazo=12, col_trazo="#081018", escala=estado.get("anio_escala", 1.0))
        # titular
        tit = estado.get("titular")
        if tit:
            estilos = {"alerta": ("#FFFFFF", "#C1121F"), "nota": ("#14212B", "#F4F1EA"), "dato": ("#14212B", "#FFD166")}
            ct, cc = estilos.get(tit["estilo"], estilos["nota"])
            self._caja_texto(canvas, tit["texto"], self.W / 2, self.H * self.lay["y_titular"], tit.get("tam", 54),
                             ct, cc, tit["alfa"], tit["escala"])
        self._subtitulos(canvas, estado.get("subtitulos"), t)
        cred = self.ep.get("credito")
        if cred:
            self._texto_centrado(canvas, cred, self.W / 2, self.H * self.lay["y_credito"], 22, "#C5CED6",
                                 peso="SemiBold", alfa=0.75)
        marca = self.ep.get("marca")
        if marca:
            self._texto_centrado(canvas, marca, self.W / 2, self.H * self.lay["y_credito"] + 34 * self.u, 26,
                                 "#FFFFFF", peso="Bold", alfa=0.8)
        return self.superficie.makeImageSnapshot().toarray()


def palabras_de(texto):
    return [p for p in re.split(r"\s+", texto.strip()) if p]
