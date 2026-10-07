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


def test_palabras_desde_alineacion_elevenlabs():
    from fabrica.voz import palabras_desde_alineacion
    texto = "Hola mundo, sí."
    n = len(texto)
    al = {"characters": list(texto), "character_start_times_seconds": [i * 0.1 for i in range(n)],
          "character_end_times_seconds": [i * 0.1 + 0.1 for i in range(n)]}
    p = palabras_desde_alineacion(texto, al)
    assert [w["txt"] for w in p] == ["Hola", "mundo,", "sí."]
    assert p[0]["t0"] == 0 and p[1]["t0"] == pytest.approx(0.5) and p[-1]["t1"] == pytest.approx(1.5)


def test_buscar_frase_para_golpes():
    from fabrica.linea_tiempo import buscar_frase
    pal = [{"txt": w, "t0": i * 0.5, "t1": i * 0.5 + 0.4} for i, w in enumerate("Un impuesto de diez centavos... y una guerra.".split())]
    assert buscar_frase(pal, "diez centavos") == pytest.approx(1.5)
    assert buscar_frase(pal, "Guerra") == pytest.approx(3.5)
    assert buscar_frase(pal, "cien pesos") is None


def test_region_visible_cubre_el_encuadre():
    from fabrica.encuadre import huella, region_visible
    region = [-80, -36, -54, -8]
    # cámara vertical sobre Bolivia a altura "pais": ve más al norte de -8 y más al sur de -36
    zona = region_visible(region, [(-64.6, -16.7, 0.8, 0, 0)], 9 / 16)
    assert zona[1] < -36 and zona[3] > -8
    assert zona[0] <= -80 and zona[2] >= -54
    # desde el espacio el relieve no se ve: la región no cambia (salvo el margen)
    assert region_visible(region, [(-64.6, -16.7, 3.2, 0, 0)], 9 / 16) == [-81.5, -37.5, -52.5, -6.5]
    # la huella es simétrica en una vista cenital
    lats = [la for _, la in huella(0, 0, 0.5, 0, 0, 1.0)]
    assert abs(max(lats) + min(lats)) < 1e-6


def _alineacion_falsa(texto, dur_letra=0.05, hueco=0.4):
    """Tiempos por carácter: cada letra dura 0.05 s y después de cada punto hay 0.4 s de silencio."""
    ini, fin, t = [], [], 0.0
    for c in texto:
        ini.append(t)
        t += dur_letra
        fin.append(t)
        if c in ".?!":
            t += hueco
    return {"characters": list(texto), "character_start_times_seconds": ini, "character_end_times_seconds": fin}, t


def test_trocear_parte_en_frases_y_al_unir_queda_igual():
    import numpy as np
    from fabrica import voz
    texto = "[mysterious] Bolivia tiene armada. Pero no tiene mar. ¿Cómo es posible?"
    frs = voz.frases("Bolivia tiene armada. Pero no tiene mar. ¿Cómo es posible?")
    al, dur = _alineacion_falsa(texto)
    audio = np.arange(int(dur * voz.SR), dtype=np.float32)
    partes = voz.trocear(texto, frs, audio, al)
    assert [len(p[1]) for p in partes] == [3, 4, 3]
    assert np.array_equal(np.concatenate([p[0] for p in partes]), audio)   # sin perder ni repetir muestras
    # cada frase empieza con su primera palabra cerca del inicio del trozo (medio silencio antes)
    assert partes[1][1][0]["txt"] == "Pero" and 0.15 < partes[1][1][0]["t0"] < 0.25
    assert voz.trocear(texto, ["no está en el texto"], audio, al) is None


def test_plan_elevenlabs_pide_solo_las_frases_nuevas(tmp_path, monkeypatch):
    import numpy as np
    from fabrica import elevenlabs, voz
    from fabrica.modelo import Voz
    monkeypatch.setattr(elevenlabs, "BIBLIOTECA", tmp_path)
    cfg = Voz(motor="elevenlabs", voz="x")
    a = np.zeros(100, np.float32)
    voz._guardar_frase("Uno.", cfg, None, a, [{"txt": "Uno.", "t0": 0, "t1": 0.1}])
    voz._guardar_frase("Cuatro.", cfg, None, a, [{"txt": "Cuatro.", "t0": 0, "t1": 0.1}])
    _, clips, pedidos = voz._plan_elevenlabs("Uno. Dos. Tres. Cuatro. Cinco.", cfg, None)
    assert clips[0] is not None and clips[3] is not None
    assert pedidos == [([1, 2], "Dos. Tres."), ([4], "Cinco.")]
    assert voz.creditos_voz("Uno. Dos. Tres. Cuatro. Cinco.", cfg) == len("Dos. Tres.") + len("Cinco.")
    assert voz.creditos_voz("Uno. Cuatro.", cfg) == 0
