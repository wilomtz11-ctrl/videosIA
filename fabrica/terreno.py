"""Relieve y textura de alta resolución para la región del episodio.

- Alturas: AWS Terrain Tiles (terrarium), remuestreadas a una rejilla lon/lat regular.
- Textura: color de NASA Blue Marble × sombreado calculado del relieve (técnica cartográfica clásica);
  los lagos se pintan de azul y el océano se colorea por profundidad.
El resultado se guarda en caché según la región y los parámetros.
"""
from __future__ import annotations

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from . import datos

VERSION = 2   # súbelo si cambia el algoritmo, para invalidar la caché


def _tesela(lon, lat, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def zoom_para(region, lado):
    """Zoom de teselas suficiente para 'lado' píxeles a lo ancho de la región (máx. 9)."""
    ancho_grados = region[2] - region[0]
    return int(min(9, max(5, math.ceil(math.log2(lado / 256 * 360 / ancho_grados)))))


def elevacion(region, lado):
    """Matriz lado×lado de alturas en metros (filas de norte a sur)."""
    z = zoom_para(region, lado)
    x0, y0 = _tesela(region[0], region[3], z)
    x1, y1 = _tesela(region[2], region[1], z)
    xs, ys = range(int(x0), int(x1) + 1), range(int(y0), int(y1) + 1)
    with ThreadPoolExecutor(16) as ex:
        rutas = dict(zip([(x, y) for x in xs for y in ys],
                         ex.map(lambda xy: datos.tesela_terreno(z, *xy), [(x, y) for x in xs for y in ys])))
    mos = np.zeros((len(ys) * 256, len(xs) * 256), np.float32)
    for (x, y), ruta in rutas.items():
        a = np.asarray(Image.open(ruta).convert("RGB")).astype(np.float32)
        mos[(y - ys[0]) * 256:(y - ys[0] + 1) * 256, (x - xs[0]) * 256:(x - xs[0] + 1) * 256] = (
            a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768)
    lon = np.linspace(region[0], region[2], lado)
    lat = np.linspace(region[3], region[1], lado)
    px = ((lon + 180) / 360 * 2 ** z - xs[0]) * 256
    py = ((1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * 2 ** z - ys[0]) * 256
    ix = np.clip(px, 0, mos.shape[1] - 1).astype(int)
    iy = np.clip(py, 0, mos.shape[0] - 1).astype(int)
    return mos[iy[:, None], ix[None, :]]


def _sombreado(elev, region, z=4.0, azimut=315, altura=45):
    lado = elev.shape[0]
    celda_x = (region[2] - region[0]) / lado * 111320 * math.cos(math.radians((region[1] + region[3]) / 2))
    celda_y = (region[3] - region[1]) / lado * 110540
    gy, gx = np.gradient(elev * z, celda_y, celda_x)
    pend = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    asp = np.arctan2(-gx, gy)
    az, al = math.radians(azimut), math.radians(altura)
    return np.clip(np.sin(al) * np.sin(pend) + np.cos(al) * np.cos(pend) * np.cos(az - asp), 0, 1)


def textura(elev, region):
    marble = Image.open(datos.blue_marble()).convert("RGB")
    W, H = marble.size
    lado = elev.shape[0]
    caja = ((region[0] + 180) / 360 * W, (90 - region[3]) / 180 * H, (region[2] + 180) / 360 * W, (90 - region[1]) / 180 * H)
    color = np.asarray(marble.resize((lado, lado), Image.BICUBIC, box=caja)).astype(np.float32) / 255
    sh = _sombreado(elev, region)[..., None]
    tierra = elev > 0
    out = color * (0.45 + 0.85 * sh)
    lago = tierra & (color.mean(axis=2) < 0.09)
    out = np.where(lago[..., None], np.array([0.10, 0.26, 0.42]) * (0.85 + 0.2 * sh), out)
    prof = np.clip(-elev / 6000, 0, 1)[..., None]
    mar = np.array([0.07, 0.24, 0.42]) * (1 - prof) + np.array([0.02, 0.08, 0.20]) * prof
    mar = mar * (0.8 + 0.3 * _sombreado(elev, region, z=1.0)[..., None])
    out = np.where(tierra[..., None], out, mar)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


def preparar(region, destino: Path, lado_textura=4096, rejilla=384) -> dict:
    """Escribe textura.jpg y relieve.bin en 'destino' (desde caché si ya existen)."""
    clave = hashlib.sha1(json.dumps([VERSION, list(region), lado_textura, rejilla]).encode()).hexdigest()[:12]
    cache = datos.DATOS / "cache_terreno" / clave
    if not (cache / "relieve.bin").exists():
        cache.mkdir(parents=True, exist_ok=True)
        print(f"  relieve: descargando y procesando región {region}...")
        elev = elevacion(region, lado_textura)
        textura(elev, region).save(cache / "textura.jpg", quality=90)
        paso = lado_textura // rejilla
        malla = elev[: paso * rejilla, : paso * rejilla].reshape(rejilla, paso, rejilla, paso).max(axis=(1, 3))
        np.maximum(malla, 0).astype(np.float32).tofile(cache / "relieve.bin")
    destino.mkdir(parents=True, exist_ok=True)
    for f in ("textura.jpg", "relieve.bin"):
        (destino / f).write_bytes((cache / f).read_bytes())
    return {"rejilla": rejilla}
