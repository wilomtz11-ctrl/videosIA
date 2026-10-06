"""Fronteras históricas: descarga, caché, recorte y formas derivadas.

Los datos vienen de historical-basemaps (Andre Ourednik, GPL-3.0):
https://github.com/aourednik/historical-basemaps
"""
import json
import urllib.request
from pathlib import Path

from shapely.geometry import box, shape
from shapely.ops import unary_union

URL = "https://raw.githubusercontent.com/aourednik/historical-basemaps/master/geojson/world_{}.geojson"
DATOS = Path(__file__).resolve().parent.parent / "datos"

_cache = {}


def ruta_anio(anio):
    """Devuelve la ruta local del GeoJSON del año; lo descarga si falta."""
    DATOS.mkdir(exist_ok=True)
    ruta = DATOS / f"world_{anio}.geojson"
    if not ruta.exists():
        print(f"  descargando fronteras de {anio}...")
        urllib.request.urlretrieve(URL.format(anio), ruta)
    return ruta


def cargar(anio, region, tolerancia=0.02):
    """Países de un año recortados a la región [lon0, lat0, lon1, lat1].

    Devuelve {nombre: geometría}. Si un nombre aparece en varias piezas, se unen.
    """
    clave = (anio, tuple(region), tolerancia)
    if clave in _cache:
        return _cache[clave]
    caja = box(*region)
    datos = json.load(open(ruta_anio(anio), encoding="utf-8"))
    piezas = {}
    for f in datos["features"]:
        try:
            g = shape(f["geometry"]).buffer(0)
        except Exception:
            continue
        if g.is_empty or not g.intersects(caja):
            continue
        nombre = f["properties"].get("NAME") or "?"
        piezas.setdefault(nombre, []).append(g.intersection(caja))
    paises = {}
    for nombre, gs in piezas.items():
        g = unary_union(gs).simplify(tolerancia, preserve_topology=True)
        if not g.is_empty:
            paises[nombre] = g
    _cache[clave] = paises
    return paises


def _ref(texto, region):
    """'1878:Bolivia' -> geometría de Bolivia en 1878."""
    anio, nombre = texto.split(":", 1)
    paises = cargar(int(anio), region)
    if nombre not in paises:
        raise KeyError(f"'{nombre}' no existe en el mapa de {anio}. Hay: {sorted(paises)}")
    return paises[nombre]


def poligonos(g):
    """Lista de polígonos simples de cualquier geometría."""
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [p for parte in getattr(g, "geoms", []) for p in poligonos(parte)]


def forma_derivada(defin, region):
    """Construye una forma a partir de operaciones entre países de distintos años.

    defin = {"op": "interseccion" | "diferencia" | "union", "a": "1878:Bolivia",
             "b": "2010:Chile", "filtro": [lon0, lat0, lon1, lat1], "area_min": 0.05}
    """
    a = _ref(defin["a"], region)
    if defin["op"] == "pais":
        g = a
    else:
        b = _ref(defin["b"], region)
        g = {"interseccion": a.intersection, "diferencia": a.difference, "union": a.union}[defin["op"]](b)
    g = g.buffer(0)
    filtro = defin.get("filtro")
    area_min = defin.get("area_min", 0.05)
    partes = [p for p in poligonos(g) if p.area >= area_min and (filtro is None or box(*filtro).contains(p.representative_point()))]
    return unary_union(partes) if partes else g.intersection(box(0, 0, 0, 0))
