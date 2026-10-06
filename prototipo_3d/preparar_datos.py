"""Prepara los datos del prototipo 3D (todo libre):

- Relieve: Terrain Tiles de AWS (Mapzen/Tilezen, formato terrarium). Requiere atribución.
- Color: NASA Blue Marble (dominio público).
- Fronteras actuales: Natural Earth (dominio público).
- Litoral perdido: historical-basemaps (GPL-3.0), calculado con videosia.geo.

Genera en assets/:
  relieve.bin    alturas (float32, metros) de una malla REJILLA×REJILLA sobre la región
  textura.jpg    color satelital + sombreado de relieve en alta resolución
  mascaras.png   R = Bolivia, G = litoral boliviano de 1878 (para iluminarlos en el shader)
  paises.json    fronteras actuales (líneas) · bolivia.json · litoral.json
  region.json    límites de la región
  efectos.wav    efectos de sonido sintetizados
"""
import io
import json
import math
import shutil
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from videosia import geo  # noqa: E402

ASSETS = AQUI / "assets"
CACHE = AQUI.parent / "datos" / "terrarium"
REGION = (-77.0, -29.0, -55.0, -8.0)      # lon0, lat0, lon1, lat1
ZOOM = 8                                    # teselas de relieve (~600 m/píxel)
TEX = 4096                                  # lado de la textura
REJILLA = 512                               # vértices por lado de la malla
URL_TERRENO = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
URL_MARBLE = "https://raw.githubusercontent.com/vasturiano/three-globe/master/example/img/earth-blue-marble.jpg"
URL_PAISES = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"


def bajar(url, ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, ruta)
    return ruta


def tesela(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def mosaico_relieve():
    """Mosaico de teselas terrarium -> elevación en rejilla equirectangular TEX×TEX."""
    x0, y0 = tesela(REGION[0], REGION[3], ZOOM)
    x1, y1 = tesela(REGION[2], REGION[1], ZOOM)
    xs, ys = range(int(x0), int(x1) + 1), range(int(y0), int(y1) + 1)
    trabajos = [(x, y) for x in xs for y in ys]

    def uno(xy):
        x, y = xy
        return xy, bajar(URL_TERRENO.format(z=ZOOM, x=x, y=y), CACHE / str(ZOOM) / str(x) / f"{y}.png")

    with ThreadPoolExecutor(16) as ex:
        rutas = dict(ex.map(uno, trabajos))
    print(f"  {len(trabajos)} teselas de relieve")
    mos = np.zeros((len(ys) * 256, len(xs) * 256), np.float32)
    for (x, y), ruta in rutas.items():
        a = np.asarray(Image.open(ruta).convert("RGB")).astype(np.float32)
        elev = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
        mos[(y - ys[0]) * 256:(y - ys[0] + 1) * 256, (x - xs[0]) * 256:(x - xs[0] + 1) * 256] = elev
    # remuestreo a rejilla lon/lat regular
    lon = np.linspace(REGION[0], REGION[2], TEX)
    lat = np.linspace(REGION[3], REGION[1], TEX)
    px = np.array([tesela(l, 0, ZOOM)[0] for l in lon]) - xs[0]
    py = np.array([tesela(0, l, ZOOM)[1] for l in lat]) - ys[0]
    ix = np.clip(px * 256, 0, mos.shape[1] - 1).astype(int)
    iy = np.clip(py * 256, 0, mos.shape[0] - 1).astype(int)
    return mos[iy[:, None], ix[None, :]]


def sombreado(elev, azimut=315, altura=45, z=4.0):
    cell = (REGION[2] - REGION[0]) / TEX * 111000 * math.cos(math.radians((REGION[1] + REGION[3]) / 2))
    gy, gx = np.gradient(elev * z, cell)
    pend = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    asp = np.arctan2(-gx, gy)
    az, al = math.radians(azimut), math.radians(altura)
    s = np.sin(al) * np.sin(pend) + np.cos(al) * np.cos(pend) * np.cos(az - asp)
    return np.clip(s, 0, 1)


def textura(elev):
    marble = Image.open(bajar(URL_MARBLE, CACHE.parent / "blue-marble.jpg")).convert("RGB")
    W, H = marble.size
    caja = ((REGION[0] + 180) / 360 * W, (90 - REGION[3]) / 180 * H, (REGION[2] + 180) / 360 * W, (90 - REGION[1]) / 180 * H)
    color = np.asarray(marble.crop(tuple(int(round(c)) for c in caja)).resize((TEX, TEX), Image.BICUBIC)).astype(np.float32) / 255
    sh = sombreado(elev)[..., None]
    tierra = elev > 0
    # tierra: color satelital modulado por el sombreado (contraste suave)
    out = color * (0.45 + 0.85 * sh)
    # océano: azul profundo según profundidad, con el mismo sombreado sutil
    prof = np.clip(-elev / 6000, 0, 1)[..., None]
    mar = np.array([0.07, 0.24, 0.42]) * (1 - prof) + np.array([0.02, 0.08, 0.20]) * prof
    mar = mar * (0.8 + 0.3 * sombreado(elev, z=1.0)[..., None])
    # lagos (Titicaca, Poopó): en Blue Marble salen casi negros; se pintan de azul
    lago = tierra & (color.mean(axis=2) < 0.09)
    out = np.where(lago[..., None], np.array([0.10, 0.26, 0.42]) * (0.85 + 0.2 * sh), out)
    out = np.where(tierra[..., None], out, mar)
    # costa: mezcla suave para evitar bordes duros
    out = np.clip(out, 0, 1)
    img = Image.fromarray((out * 255).astype(np.uint8))
    img.save(ASSETS / "textura.jpg", quality=90)


def a_pixel(lon, lat, n):
    return ((lon - REGION[0]) / (REGION[2] - REGION[0]) * n, (REGION[3] - lat) / (REGION[3] - REGION[1]) * n)


def mascara(geom, n=2048):
    im = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(im)
    for p in geo.poligonos(geom):
        d.polygon([a_pixel(x, y, n) for x, y in p.exterior.coords], fill=255)
        for hueco in p.interiors:
            d.polygon([a_pixel(x, y, n) for x, y in hueco.coords], fill=0)
    return im.filter(ImageFilter.GaussianBlur(1.5))


def a_geojson(geom, ruta):
    from shapely.geometry import mapping
    json.dump({"type": "Feature", "properties": {}, "geometry": mapping(geom)}, open(ruta, "w"))


def main():
    ASSETS.mkdir(exist_ok=True)
    print("[1/5] Relieve (AWS Terrain Tiles)")
    elev = mosaico_relieve()
    print("[2/5] Textura")
    textura(elev)
    print("[3/5] Malla de alturas")
    paso = TEX // REJILLA
    malla = elev.reshape(REJILLA, paso, REJILLA, paso).max(axis=(1, 3))  # max conserva las cumbres
    malla = np.where(malla > 0, malla, 0).astype(np.float32)
    malla.tofile(ASSETS / "relieve.bin")
    print("[4/5] Fronteras y máscaras")
    caja_hb = [-92, -58, -30, 15]
    from shapely import force_2d
    litoral = force_2d(geo.forma_derivada({"op": "interseccion", "a": "1878:Bolivia", "b": "2010:Chile",
                                           "filtro": [-72, -25.5, -66, -20.5]}, caja_hb))
    paises = json.load(open(bajar(URL_PAISES, CACHE.parent / "ne_50m_admin_0_countries.geojson"), encoding="utf-8"))
    from shapely.geometry import shape
    bolivia = next(shape(f["geometry"]) for f in paises["features"] if f["properties"]["ADMIN"] == "Bolivia")
    a_geojson(litoral, ASSETS / "litoral.json")
    a_geojson(bolivia, ASSETS / "bolivia.json")
    lineas = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"n": f["properties"]["ADMIN"]}, "geometry": f["geometry"]}
        for f in paises["features"]]}
    json.dump(lineas, open(ASSETS / "paises.json", "w"))
    r, g = mascara(bolivia), mascara(litoral)
    Image.merge("RGB", (r, g, Image.new("L", r.size, 0))).save(ASSETS / "mascaras.png")
    json.dump({"region": REGION, "rejilla": REJILLA}, open(ASSETS / "region.json", "w"))
    print("[5/5] Bibliotecas y recursos")
    shutil.copy(bajar(URL_MARBLE, CACHE.parent / "blue-marble.jpg"), ASSETS / "blue-marble.jpg")
    nm = AQUI / "node_modules" / "three" / "build"
    for f in ("three.module.js", "three.core.js"):
        shutil.copy(nm / f, ASSETS / f)
    for f in ("Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf"):
        shutil.copy(AQUI.parent / "fuentes" / f, ASSETS / f)
    efectos()
    print("Listo.")


def efectos(dur=14):
    """Efectos de sonido sincronizados con index.html (sintetizados: sin derechos de terceros)."""
    import soundfile as sf
    from videosia import audio
    n = dur * audio.SR
    t = np.arange(n) / audio.SR
    mezcla = (0.06 * np.sin(2 * np.pi * 55 * t) + 0.04 * np.sin(2 * np.pi * 82.4 * t)
              + 0.02 * np.sin(2 * np.pi * 110 * t * (1 + 0.002 * np.sin(t))))
    mezcla = (mezcla * np.clip(t / 2, 0, 1) * np.clip((dur - t) / 1.5, 0, 1)).astype(np.float32)

    def poner(clip, seg, gan=1.0):
        i = int(seg * audio.SR)
        mezcla[i:i + len(clip)] += clip[:max(0, n - i)] * gan

    poner(audio.pop(), 0.3, 0.8)
    poner(audio.whoosh(1.4, 2), 2.6, 0.9)
    poner(audio.whoosh(1.0, 5), 6.3, 0.8)
    poner(audio.pop(), 7.8, 0.7)
    poner(audio.impacto(), 10.4, 1.0)
    poner(audio.pop(), 10.6, 0.6)
    mezcla = np.clip(mezcla, -1, 1)
    sf.write(ASSETS / "efectos.wav", np.stack([mezcla, mezcla], axis=1), audio.SR)


if __name__ == "__main__":
    main()
