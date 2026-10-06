"""Descarga con caché de las fuentes de datos libres. Todo queda en datos/ (ignorado por git)."""
from __future__ import annotations

import json
import urllib.request
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"

NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
HISTORICO = "https://raw.githubusercontent.com/aourednik/historical-basemaps/master/geojson/world_{}.geojson"
TERRENO = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
MARBLE = "https://raw.githubusercontent.com/vasturiano/three-globe/master/example/img/earth-blue-marble.jpg"

# Créditos que deben aparecer en el video o en la descripción
CREDITOS = {
    "terreno": "Relieve: AWS Terrain Tiles (Mapzen)",
    "marble": "Imagen: NASA Blue Marble",
    "ne": "Fronteras: Natural Earth",
    "historico": "Mapas históricos: historical-basemaps (A. Ourednik)",
}


def bajar(url: str, ruta: Path) -> Path:
    """Descarga una vez; escribe a un temporal y renombra para no dejar archivos a medias."""
    if ruta.exists() and ruta.stat().st_size > 0:
        return ruta
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while bloque := r.read(1 << 20):
            f.write(bloque)
    tmp.replace(ruta)
    return ruta


@lru_cache(maxsize=None)
def natural_earth(capa: str) -> dict:
    return json.loads(bajar(NE.format(capa), DATOS / "ne" / f"{capa}.geojson").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def historico(anio: int) -> dict:
    return json.loads(bajar(HISTORICO.format(anio), DATOS / f"world_{anio}.geojson").read_text(encoding="utf-8"))


def tesela_terreno(z: int, x: int, y: int) -> Path:
    return bajar(TERRENO.format(z=z, x=x, y=y), DATOS / "terrarium" / str(z) / str(x) / f"{y}.png")


MARBLE_HD = [   # NASA Blue Marble Next Generation (diciembre, con relieve y batimetría), 21600×10800, dominio público
    "https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/world.topo.bathy.200412.3x21600x10800.jpg",
    "https://eoimages.gsfc.nasa.gov/images/imagerecords/74000/74142/world.topo.200412.3x21600x10800.jpg",
    "https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-topography/december/world.topo.200412.3x21600x10800.jpg",
]


def blue_marble(hd: bool = False) -> Path:
    """Imagen base del planeta. Con hd=True intenta la original de la NASA (21600 px) y si no hay acceso usa la de 4096 px."""
    if hd:
        destino = DATOS / "blue-marble-21600.jpg"
        for url in MARBLE_HD:
            try:
                return bajar(url, destino)
            except OSError as e:
                print(f"  (sin acceso a {url.split('/')[2]}: {e.__class__.__name__})")
        print("  aviso: uso Blue Marble de 4096 px; permite el acceso a eoimages.gsfc.nasa.gov para máxima nitidez")
    return bajar(MARBLE, DATOS / "blue-marble.jpg")
