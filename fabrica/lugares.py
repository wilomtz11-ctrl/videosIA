"""Convierte nombres ("Bolivia", "Calama", "Lago Titicaca", "Océano Pacífico") en coordenadas y geometrías.

Orden de búsqueda: lugares propios del episodio > países > lagos > mares > ciudades.
Nombres en español o inglés, sin importar tildes ni mayúsculas.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import cached_property

from shapely.geometry import Point, box, shape
from shapely.ops import polylabel
from shapely.ops import unary_union

from . import datos
from .geometria import poligonos


def normal(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()
    return " ".join(s.replace("-", " ").split())


@dataclass(frozen=True)
class Lugar:
    nombre: str          # nombre para mostrar (en español)
    lon: float
    lat: float
    tipo: str            # pais | ciudad | agua | propio


class Lugares:
    def __init__(self, region, propios: dict | None = None):
        self.region = region
        self.caja = box(*region)
        self.propios = {normal(k): Lugar(k, v[0], v[1], "propio") for k, v in (propios or {}).items()}

    @cached_property
    def _paises(self):
        idx = {}
        for f in datos.natural_earth("ne_50m_admin_0_countries")["features"]:
            p = f["properties"]
            es = p.get("NAME_ES") or p["NAME"]
            entrada = (es, (p["LABEL_X"], p["LABEL_Y"]), f["geometry"])
            for n in {p["NAME"], p["ADMIN"], es}:
                idx.setdefault(normal(n), entrada)
        return idx

    @cached_property
    def _aguas(self):
        idx = {}
        for capa in ("ne_50m_lakes", "ne_50m_geography_marine_polys"):
            for f in datos.natural_earth(capa)["features"]:
                p = f["properties"]
                es = p.get("name_es") or p.get("name")
                if not p.get("name"):
                    continue
                for n in {p["name"], es}:
                    if n:
                        idx.setdefault(normal(n), []).append((es, f["geometry"]))
        return idx

    @cached_property
    def _ciudades(self):
        idx = {}
        for f in datos.natural_earth("ne_10m_populated_places_simple")["features"]:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            for n in {p["name"], p.get("nameascii") or p["name"]}:
                idx.setdefault(normal(n), []).append((p["name"], lon, lat, p.get("pop_max") or 0))
        return idx

    def buscar(self, nombre: str) -> Lugar:
        n = normal(nombre)
        if n in self.propios:
            return self.propios[n]
        if n in self._paises:
            es, (lon, lat), geom = self._paises[n]
            if not self.caja.contains(Point(lon, lat)):   # etiqueta oficial fuera de la región: usa la parte visible
                parte = shape(geom).buffer(0).intersection(self.caja)
                if not parte.is_empty:
                    p = polylabel(max(poligonos(parte), key=lambda q: q.area), tolerance=0.05)
                    lon, lat = p.x, p.y
            return Lugar(es, lon, lat, "pais")
        sin_prefijo = n.removeprefix("lago ").removeprefix("oceano ").removeprefix("mar ")
        for clave in (n, sin_prefijo):
            if clave in self._aguas:
                es, geom = self._aguas[clave][0]
                g = shape(geom).buffer(0)
                parte = g.intersection(self.caja)
                if not parte.is_empty:
                    p = parte.representative_point()
                else:
                    # los polígonos de mares de Natural Earth son zonas de etiqueta lejanas:
                    # se usa el punto de agua de la región más cercano a ese mar
                    p = min(self._puntos_agua(), key=lambda q: q.distance(g))
                return Lugar(nombre if "oceano" in n or "lago" in n else es, p.x, p.y, "agua")
        if n in self._ciudades:
            cands = self._ciudades[n]
            dentro = [c for c in cands if self.caja.contains(Point(c[1], c[2]))]
            nom, lon, lat, _ = max(dentro or cands, key=lambda c: c[3])
            return Lugar(nom, lon, lat, "ciudad")
        raise KeyError(f"No encontré el lugar '{nombre}'. Agrégalo en 'lugares' del episodio como [lon, lat].")

    def _puntos_agua(self):
        x0, y0, x1, y1 = self.region
        tierra = unary_union([shape(e[2]).buffer(0) for e in {id(v): v for v in self._paises.values()}.values()
                              if shape(e[2]).intersects(self.caja)]).buffer(0.6)
        pts = [Point(x0 + (x1 - x0) * (i + 0.5) / 24, y0 + (y1 - y0) * (j + 0.5) / 24) for i in range(24) for j in range(24)]
        return [p for p in pts if not tierra.contains(p)] or [self.caja.centroid]

    def punto(self, valor) -> tuple[float, float]:
        if isinstance(valor, (tuple, list)):
            return float(valor[0]), float(valor[1])
        lug = self.buscar(valor)
        return lug.lon, lug.lat

    def geometria_pais(self, nombre: str):
        n = normal(nombre)
        if n not in self._paises:
            raise KeyError(f"'{nombre}' no es un país de Natural Earth")
        return shape(self._paises[n][2]).buffer(0)

    def nombre_es(self, nombre_dataset: str) -> str:
        """Nombre en español de un país de cualquier dataset (si Natural Earth lo conoce)."""
        n = normal(nombre_dataset)
        return self._paises[n][0] if n in self._paises else nombre_dataset

    def union_paises(self, nombres):
        return unary_union([self.geometria_pais(x) for x in nombres])
