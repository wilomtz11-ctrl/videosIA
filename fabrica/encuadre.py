"""Zona que realmente ve la cámara: el relieve y los mapas deben cubrirla entera.

Si la región del guion es más chica que el encuadre (pasa mucho en vertical), arriba y abajo
se ve el globo sin colores y queda una franja oscura. Aquí se calcula la huella de la cámara
en cada escena (misma geometría que motor3d/motor.js) y se agranda la región para cubrirla.
"""
from __future__ import annotations

import math

import numpy as np

FOV = 38            # grados verticales, igual que la PerspectiveCamera del motor
ALT_PARCHE = 2.2    # por encima de esta altura el relieve ya no se ve (motor.js: 1.3 + 0.9)
MARGEN = 1.5        # grados extra alrededor


def _v3(lon, lat):
    f, lo = math.radians(lat), math.radians(lon)
    return np.array([math.cos(f) * math.sin(lo), math.sin(f), math.cos(f) * math.cos(lo)])


def huella(lon, lat, alt, incl, rumbo, aspecto, foco_y=0.0, n=12) -> list[tuple[float, float]]:
    """Puntos (lon, lat) del suelo en el borde del cuadro. Los rayos que miran al cielo
    se reemplazan por el punto del globo más cercano (el horizonte). foco_y: desplazamiento vertical
    del encuadre (camera.setViewOffset en el motor), en fracción de la altura del cuadro."""
    obj = _v3(lon, lat)
    lo, f = math.radians(lon), math.radians(lat)
    este = np.array([math.cos(lo), 0, -math.sin(lo)])
    norte = np.array([-math.sin(f) * math.sin(lo), math.cos(f), -math.sin(f) * math.cos(lo)])
    d = norte * math.cos(math.radians(rumbo)) + este * math.sin(math.radians(rumbo))
    p = math.radians(incl)
    cam = obj + obj * alt * math.cos(p) - d * alt * math.sin(p)
    adelante = (obj - cam) / np.linalg.norm(obj - cam)
    arriba = obj * math.sin(p) + d * math.cos(p)
    arriba -= adelante * arriba.dot(adelante)
    arriba /= np.linalg.norm(arriba)
    derecha = np.cross(adelante, arriba)
    tv = math.tan(math.radians(FOV / 2))
    th = tv * aspecto
    borde = [(x, y) for x in np.linspace(-1, 1, n) for y in (-1, 1)] + [(x, y) for y in np.linspace(-1, 1, n) for x in (-1, 1)]
    puntos = []
    for x, y in borde:
        r = adelante + derecha * x * th + arriba * (y - 2 * foco_y) * tv
        r /= np.linalg.norm(r)
        b = cam.dot(r)
        disc = b * b - (cam.dot(cam) - 1)
        q = cam + r * (-b - math.sqrt(disc)) if disc >= 0 and -b > 0 else cam - r * b
        q /= np.linalg.norm(q)
        puntos.append((math.degrees(math.atan2(q[0], q[2])), math.degrees(math.asin(max(-1.0, min(1.0, q[1]))))))
    return puntos


def region_visible(region, camaras, aspecto, foco_y=0.0) -> list[float]:
    """Región del guion agrandada para cubrir lo que ve la cámara de cerca.
    camaras: [(lon, lat, alt, incl, rumbo)]; aspecto = ancho / alto."""
    lon0, lat0, lon1, lat1 = region
    for c in camaras:
        if c[2] >= ALT_PARCHE:
            continue
        for lo, la in huella(*c, aspecto, foco_y):
            if abs(lo - c[0]) > 180:   # no cruzar el antimeridiano
                continue
            lon0, lon1, lat0, lat1 = min(lon0, lo), max(lon1, lo), min(lat0, la), max(lat1, la)
    return [round(max(-180.0, lon0 - MARGEN), 2), round(max(-85.0, lat0 - MARGEN), 2),
            round(min(180.0, lon1 + MARGEN), 2), round(min(85.0, lat1 + MARGEN), 2)]
