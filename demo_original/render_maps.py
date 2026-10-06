import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly
from shapely.geometry import shape, box

BOX = box(-84, -57, -32, 14)
W, H = 1080, 1920
# encuadre del mapa (longitud/latitud)
LON0, LON1, LAT0, LAT1 = -84, -32, -57, 14

NAMES = {
 1800: {"Viceroyalty of New Granada":"Virreinato de\nNueva Granada","Viceroyalty of Peru":"Virreinato\ndel Perú",
        "Viceroyalty of the Río de la Plata":"Virreinato del\nRío de la Plata","Viceroyalty of Brazil":"Brasil\n(Portugal)",
        "Paraguay":"Paraguay","Pampas cultures":"Pueblos\nindígenas","Patagonian shellfish and marine mammal hunters":"Pueblos\nindígenas",
        "Shuar":"","British Guiana":"","United Kingdom":"","Viceroyalty of New Spain":""},
 1815: {"Viceroyalty of New Granada":"Virreinato de\nNueva Granada","Viceroyalty of Peru":"Virreinato\ndel Perú",
        "United Provinces of the Río de la Plata":"Provincias Unidas\ndel Río de la Plata","Viceroyalty of Brazil":"Brasil\n(Portugal)",
        "Paraguay":"Paraguay","Pampas cultures":"Pueblos\nindígenas","Patagonian shellfish and marine mammal hunters":"Pueblos\nindígenas",
        "Shuar":"","Guiana":"","United Kingdom":"","Viceroyalty of New Spain":""},
}
MODERN = {"Argentina":"Argentina","Bolivia":"Bolivia","Brazil":"Brasil","Kingdom of Brazil":"Imperio\ndel Brasil","Chile":"Chile",
          "Colombia":"Colombia","Ecuador":"Ecuador","Paraguay":"Paraguay","Peru":"Perú","Uruguay":"Uruguay","Venezuela":"Venezuela",
          "Guyana":"","Suriname":"","French Guiana":"","British Guiana":"","Dutch Guiana":"","Panama":"","Costa Rica":"","Nicaragua":"",
          "United Kingdom of Great Britain and Ireland":""}
COLORS = {
 "Viceroyalty of New Granada":"#E07A5F","Viceroyalty of Peru":"#D4A373","Viceroyalty of the Río de la Plata":"#E9C46A",
 "United Provinces of the Río de la Plata":"#8AB6D6","Viceroyalty of Brazil":"#81B29A","Paraguay":"#B5838D",
 "Argentina":"#8AB6D6","Bolivia":"#F4A261","Brazil":"#81B29A","Kingdom of Brazil":"#81B29A","Chile":"#E76F51","Colombia":"#F2CC8F",
 "Ecuador":"#FFD166","Peru":"#D4A373","Uruguay":"#A8DADC","Venezuela":"#E07A5F",
}
DEFAULT = "#C9C2B2"; INDIG = "#E8DFC9"
OCEAN = "#0E1E2B"
COLONIAL = [("Virreinato de\nNueva Granada",-69.5,5.0,22,0,0),("Virreinato\ndel Perú",-71.5,-11,22,0,0),
            ("Brasil\n(Portugal)",-50,-9,30,0,0),("Paraguay",-58.3,-23.2,15,0,0),("Pueblos\nindígenas",-69.3,-45.5,14,0,0)]
MOD = [("Colombia",-73.3,4.3,22,0,0),("Venezuela",-65.5,7.3,20,0,0),("Ecuador",-78.2,-1.7,14,0,0),("Perú",-75,-9.5,22,0,0),
       ("Bolivia",-64.8,-17,22,0,0),("Paraguay",-58.3,-23.2,15,0,0),("Argentina",-65,-35,26,0,0),("Uruguay",-55.9,-32.8,12,0,0),
       ("Chile",-78.5,-33,24,1,90)]
LABELS = {
 1800: COLONIAL+[("Virreinato del\nRío de la Plata",-63.5,-31,20,0,0)],
 1815: COLONIAL+[("Provincias Unidas\ndel Río de la Plata",-63.5,-31,17,0,0)],
 1880: MOD+[("Imperio\ndel Brasil",-50,-9,28,0,0)],
 1914: MOD+[("Brasil",-50,-9,30,0,0)],
 2010: MOD+[("Brasil",-50,-9,30,0,0)],
}

def draw(year, out):
    d = json.load(open(f"world_{year}.geojson"))
    fig = plt.figure(figsize=(W/100, H/100), dpi=100)
    ax = fig.add_axes([0,0,1,1]); ax.set_facecolor(OCEAN); fig.patch.set_facecolor(OCEAN)
    # el mapa ocupa de y=300 a y=1760 px
    top, bot = 300, 1760
    h_px = bot - top
    scale = h_px / (LAT1 - LAT0)
    w_px = (LON1 - LON0) * scale
    x_off = (W - w_px) / 2
    def proj(lon, lat):
        return x_off + (lon - LON0) * scale, H - (top + (LAT1 - lat) * scale)
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    labels = []
    for f in d["features"]:
        try: g = shape(f["geometry"]).buffer(0)
        except Exception: continue
        if not g.intersects(BOX): continue
        g = g.intersection(BOX).simplify(0.03)
        if g.is_empty: continue
        n = f["properties"].get("NAME") or ""
        col = COLORS.get(n, INDIG if ("cultures" in n or "hunters" in n or n=="Shuar") else DEFAULT)
        polys = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
        for p in polys:
            xy = [proj(x, y) for x, y in p.exterior.coords]
            ax.add_patch(MPoly(xy, closed=True, fc=col, ec="#1B2B38", lw=1.6))
    for (lab, lon, lat, fs, white, rot) in LABELS[year]:
        x, y = proj(lon, lat)
        ax.text(x, y, lab, ha="center", va="center", fontsize=fs, fontweight="bold",
                color="#F4F1EA" if white else "#14212B", rotation=rot,
                fontfamily="DejaVu Sans", linespacing=1.0)
    fig.savefig(out, dpi=100, facecolor=OCEAN); plt.close(fig)

for y in [1800, 1815, 1880, 1914, 2010]:
    draw(y, f"map_{y}.png"); print("ok", y)
