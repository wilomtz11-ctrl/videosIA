"""Capas que el motor 3D dibuja sobre el relieve:

- Máscaras de formas (hasta 8, en 2 PNG RGBA: un canal por forma) para resaltar o pintar zonas.
- Mapas políticos por año: PNG RGBA con el color de cada país (se funden con el relieve).
- Fronteras como segmentos [lon, lat, lon, lat, ...] por mapa (el motor las pega al relieve).
"""
from __future__ import annotations

import colorsys
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import box, shape
from shapely.ops import unary_union

from . import datos
from .geometria import poligonos
from .lugares import Lugares, normal

# Colores fijos para países frecuentes (consistentes entre episodios); el resto se asigna por hash
COLORES_PAISES = {
    "bolivia": "#F4D35E", "chile": "#E5534B", "peru": "#B79CD9", "argentina": "#8AB6D6", "brasil": "#81B29A",
    "brazil": "#81B29A", "kingdom of brazil": "#81B29A", "paraguay": "#C99AA4", "uruguay": "#A8DADC",
    "ecuador": "#F2B880", "colombia": "#D4A373", "venezuela": "#E07A5F",
}


def _color_auto(nombre: str) -> str:
    h = int(hashlib.md5(normal(nombre).encode()).hexdigest()[:6], 16) / 0xFFFFFF
    r, g, b = colorsys.hls_to_rgb(h, 0.68, 0.45)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def paises_de_mapa(anio: int, caja) -> dict:
    """{nombre: geometría} recortado a la caja. anio 0 = actual (Natural Earth)."""
    if anio == 0:
        fuente = datos.natural_earth("ne_50m_admin_0_countries")
        clave = "ADMIN"
    else:
        fuente = datos.historico(anio)
        clave = "NAME"
    out = {}
    for f in fuente["features"]:
        try:
            g = shape(f["geometry"]).buffer(0)
        except Exception:
            continue
        if g.is_empty or not g.intersects(caja):
            continue
        n = f["properties"].get(clave) or "?"
        out.setdefault(n, []).append(g.intersection(caja))
    return {k: unary_union(v).simplify(0.01) for k, v in out.items()}


def forma(defin, lugares: Lugares, region):
    """Geometría de una forma del episodio."""
    caja = box(*region).buffer(8)
    if defin.pais:
        if defin.anio:
            paises = paises_de_mapa(defin.anio, caja)
            if defin.pais not in paises:
                raise KeyError(f"'{defin.pais}' no está en el mapa de {defin.anio}: {sorted(paises)}")
            g = paises[defin.pais]
        else:
            g = lugares.geometria_pais(defin.pais)
    else:
        def ref(txt):
            anio, nombre = txt.split(":", 1)
            paises = paises_de_mapa(int(anio), caja)
            if nombre not in paises:
                raise KeyError(f"'{nombre}' no está en el mapa de {anio}: {sorted(paises)}")
            return paises[nombre]
        a, b = ref(defin.a), ref(defin.b)
        g = {"interseccion": a.intersection, "diferencia": a.difference, "union": a.union}[defin.op](b).buffer(0)
        if defin.filtro:
            f = box(*defin.filtro)
            g = unary_union([p for p in poligonos(g) if p.area > 0.02 and f.contains(p.representative_point())])
    if g.is_empty:
        raise ValueError("la forma quedó vacía (revisa 'filtro' o los nombres)")
    return g


def _a_pixel(region, n):
    lon0, lat0, lon1, lat1 = region
    return lambda x, y: ((x - lon0) / (lon1 - lon0) * n, (lat1 - y) / (lat1 - lat0) * n)


def _rasterizar(geom, region, n, blur=1.5):
    im = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(im)
    px = _a_pixel(region, n)
    for p in poligonos(geom):
        d.polygon([px(*c) for c in p.exterior.coords], fill=255)
        for h in p.interiors:
            d.polygon([px(*c) for c in h.coords], fill=0)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


def mascaras(formas: dict, region, destino: Path, n=2048) -> dict:
    """Escribe formas_0.png y formas_1.png. Devuelve {nombre: [textura, canal]}."""
    vacia = Image.new("L", (n, n), 0)
    canales = [vacia] * 8
    indice = {}
    for i, (nombre, g) in enumerate(formas.items()):
        canales[i] = _rasterizar(g, region, n)
        indice[nombre] = [i // 4, i % 4]
    Image.merge("RGBA", canales[:4]).save(destino / "formas_0.png")
    Image.merge("RGBA", canales[4:]).save(destino / "formas_1.png")
    return indice


def mapa_politico(clave: str, anio: int, region, colores: dict, lugares: Lugares, destino: Path, n=2048, alfa=0.42):
    """PNG RGBA con los países coloreados + archivo de fronteras en lon/lat. Devuelve metadatos."""
    caja_lineas = box(region[0] - 25, region[1] - 25, region[2] + 25, region[3] + 25)
    paises = paises_de_mapa(anio, caja_lineas)
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    px = _a_pixel(region, n)
    nombres = {}
    for nombre, g in paises.items():
        es = lugares.nombre_es(nombre)
        nombres[nombre] = es
        hexa = colores.get(nombre) or colores.get(es) or COLORES_PAISES.get(normal(es)) or COLORES_PAISES.get(normal(nombre)) or _color_auto(es)
        rgb = tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))
        for p in poligonos(g.intersection(box(*region))):
            d.polygon([px(*c) for c in p.exterior.coords], fill=rgb + (int(255 * alfa),))
    im.filter(ImageFilter.GaussianBlur(0.8)).save(destino / f"mapa_{clave}.png")
    # fronteras: segmentos de los anillos exteriores
    segs = []
    bx0, by0, bx1, by1 = caja_lineas.bounds
    en_borde = lambda x, y: min(abs(x - bx0), abs(x - bx1), abs(y - by0), abs(y - by1)) < 1e-3  # noqa: E731
    for g in paises.values():
        for p in poligonos(g):
            c = [(round(x, 3), round(y, 3)) for x, y in p.exterior.coords]
            for (x0, y0), (x1, y1) in zip(c, c[1:]):
                if not (en_borde(x0, y0) and en_borde(x1, y1)):   # descarta el corte artificial del recorte
                    segs += [x0, y0, x1, y1]
    (destino / f"lineas_{clave}.json").write_text(json.dumps(segs, separators=(",", ":")))
    return {"id": clave, "anio": anio, "paises": sorted(set(nombres.values()))}
