"""Tests rápidos (sin red ni render): guion, línea de tiempo y voz."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from fabrica.linea_tiempo import ENTRADA_VOZ, agrupar_subtitulos, compilar
from fabrica.modelo import ALTURAS, Episodio
from fabrica.voz import frases, silabas

RAIZ = Path(__file__).resolve().parent.parent


def ep_minimo(**extra):
    datos = {
        "titulo": "Prueba",
        "region": [-80, -36, -54, -8],
        "formas": {"bolivia": {"pais": "Bolivia"}},
        "escenas": [
            {"voz": "Primera escena del video.", "camara": {"ir_a": [-65, -17], "altura": "pais"}, "anio": 1825,
             "titular": "Hola", "etiquetas": [{"texto": "AQUÍ", "en": [-65, -17]}], "resaltar": ["bolivia"]},
            {"voz": "Segunda escena.", "anio": 1879, "etiquetas": [{"texto": "AQUÍ", "en": [-65, -17]}],
             "pintar": [{"forma": "bolivia", "color": "rojo"}]},
            {"voz": "Tercera.", "camara": {"ir_a": [-70, -23], "altura": "cerca"}},
        ],
    }
    datos.update(extra)
    return Episodio.model_validate(datos)


class LugaresFalsos:
    """Evita descargar Natural Earth en los tests."""
    def punto(self, v):
        return tuple(v)

    def buscar(self, v):
        raise KeyError(v)


def voces_falsas(ep, dur=3.0):
    return [{"wav": f"{e.id}.wav", "duracion": dur,
             "palabras": [{"txt": w, "t0": i * 0.4, "t1": i * 0.4 + 0.35} for i, w in enumerate(e.voz.split())]}
            for e in ep.escenas]


def compilar_minimo(ep, dur=3.0):
    return compilar(ep, voces_falsas(ep, dur), LugaresFalsos(),
                    {"rejilla": 8, "formas": {"bolivia": [0, 0]}, "mapas": [{"id": "hoy"}]}, (1080, 1920))


# ---------- modelo ----------

def test_episodio_de_ejemplo_es_valido():
    import yaml
    ep = Episodio.model_validate(yaml.safe_load((RAIZ / "episodios" / "bolivia_mar.yaml").read_text(encoding="utf-8")))
    assert len(ep.escenas) >= 10
    assert all(e.id for e in ep.escenas)
    assert ep.publicacion and ep.publicacion.fuentes


def test_alturas_con_nombre_e_inclinacion_automatica():
    ep = ep_minimo()
    c0, c2 = ep.escenas[0].camara, ep.escenas[2].camara
    assert c0.altura == ALTURAS["pais"] and c0.inclinacion == 0
    assert c2.altura == ALTURAS["cerca"] and c2.inclinacion > 30


def test_forma_desconocida_falla():
    with pytest.raises(ValidationError, match="no está definida"):
        ep_minimo(formas={})


def test_mapa_desconocido_falla():
    with pytest.raises(ValidationError, match="mapa"):
        ep_minimo(escenas=[{"voz": "Hola mundo.", "camara": {"ir_a": [0, 0]}, "mapa": "1500"}])


def test_primera_escena_necesita_camara():
    with pytest.raises(ValidationError, match="primera escena"):
        ep_minimo(escenas=[{"voz": "Sin cámara."}])


def test_color_invalido():
    with pytest.raises(ValidationError, match="color"):
        ep_minimo(escenas=[{"voz": "Hola.", "camara": {"ir_a": [0, 0]}, "resaltar": [{"forma": "bolivia", "color": "fucsia"}]}])


# ---------- línea de tiempo ----------

def test_tiempos_encadenados_y_voz_desplazada():
    comp = compilar_minimo(ep_minimo())
    ts = comp.tiempos
    assert ts[0][1] == 0
    for (_, _, fin), (_, ini, _) in zip(ts, ts[1:]):
        assert fin == pytest.approx(ini)
    assert comp.voces[1][1] == pytest.approx(ts[1][1] + ENTRADA_VOZ)
    assert comp.escena["duracion"] == pytest.approx(ts[-1][2], abs=1e-3)


def test_camara_monotona_y_arranca_en_el_espacio():
    comp = compilar_minimo(ep_minimo())
    kf = comp.escena["camara"]
    assert all(b[0] >= a[0] for a, b in zip(kf, kf[1:]))
    assert kf[0][3] == ALTURAS["espacio"]


def test_etiquetas_repetidas_se_unen():
    comp = compilar_minimo(ep_minimo())
    aqui = [e for e in comp.escena["etiquetas"] if e["texto"] == "AQUÍ"]
    assert len(aqui) == 1
    assert aqui[0]["t1"] == pytest.approx(comp.tiempos[1][2])


def test_eventos_de_formas_y_efectos():
    comp = compilar_minimo(ep_minimo())
    tipos = [e["tipo"] for e in comp.escena["formas_eventos"]]
    assert tipos == ["resaltar", "pintar"]
    assert any(n == "pop" for n, *_ in comp.efectos)       # el titular hace "pop"
    assert any(n == "whoosh" for n, *_ in comp.efectos)    # gran movimiento de cámara


def test_cambio_de_mapa_despinta():
    ep = ep_minimo(mapas={"hoy": 0, "1878": 1878})
    ep.escenas[2].mapa = "1878"
    comp = compilar_minimo(ep)
    assert comp.escena["mapas_pistas"][-1][1] == "1878"
    assert any(e["tipo"] == "despintar" for e in comp.escena["formas_eventos"])


def test_subtitulos_agrupados_sin_huecos():
    pal = [{"txt": w, "t0": i * 0.3, "t1": i * 0.3 + 0.25} for i, w in enumerate("uno dos tres, cuatro cinco seis siete.".split())]
    g = agrupar_subtitulos(pal)
    assert all(len(x["palabras"]) <= 3 for x in g)
    assert g[0]["palabras"][-1]["txt"] == "tres,"            # corta en la coma
    assert all(a["t1"] == b["t0"] for a, b in zip(g, g[1:]))


# ---------- voz ----------

def test_frases_no_cortan_en_comas():
    assert frases("Hola, mundo. ¿Qué tal? Bien... gracias!") == ["Hola, mundo.", "¿Qué tal?", "Bien...", "gracias!"]


def test_silabas_de_numeros():
    assert silabas("1879,") == 9
    assert silabas("Bolivia") == 3


def test_plantilla_es_valida():
    import yaml
    Episodio.model_validate(yaml.safe_load((RAIZ / "episodios" / "PLANTILLA.yaml").read_text(encoding="utf-8")))
