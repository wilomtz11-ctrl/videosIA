"""Utilidades de geometría compartidas."""
from shapely import force_2d


def poligonos(g):
    """Lista plana de polígonos (2D) de cualquier geometría."""
    if g is None or g.is_empty:
        return []
    g = force_2d(g)
    if g.geom_type == "Polygon":
        return [g]
    return [p for parte in getattr(g, "geoms", []) for p in poligonos(parte)]
