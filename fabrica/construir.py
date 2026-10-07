"""Construye un episodio completo: guion YAML -> MP4 + descripción.

Pasos: validar -> relieve/textura -> capas -> voz -> línea de tiempo -> audio -> render 3D -> unir audio.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from . import audio as mezclador

from . import capas, datos, encuadre, terreno, voz
from .calidad import CALIDADES
from .linea_tiempo import compilar
from .lugares import Lugares
from .modelo import Episodio

RAIZ = datos.RAIZ
MOTOR = RAIZ / "motor3d"
HYPERFRAMES = "hyperframes@0.8.136"
FORMATOS = {"vertical": (1080, 1920, "portrait"), "horizontal": (1920, 1080, "landscape")}


def cargar(ruta: Path) -> Episodio:
    with open(ruta, encoding="utf-8") as f:
        return Episodio.model_validate(yaml.safe_load(f))


def _paso(n, total, texto):
    print(f"[{n}/{total}] {texto}", flush=True)


# en vertical el punto de interés sube un 6 % del alto (queda a ~44 %), centrado en la zona que no tapan
# los botones ni la descripción de TikTok, Reels y Shorts
FOCO_Y = 0.06


def preparar(ruta_ep: Path, motor_voz: str | None = None, calidad: str = "normal",
             gastar: bool = False, audio: bool = True) -> tuple[Path, dict]:
    """Deja listo build/<episodio>/ para renderizar. Devuelve (carpeta, info)."""
    ep = cargar(ruta_ep)
    if motor_voz:
        ep.voz.motor = motor_voz
    nombre = ruta_ep.stem
    build = RAIZ / "build" / nombre
    dat = build / "datos"
    if build.exists():
        shutil.rmtree(build)
    dat.mkdir(parents=True)
    cal = CALIDADES[calidad]
    if audio and os.environ.get("ELEVENLABS_API_KEY"):   # nada se paga sin confirmar
        c_voz = sum(voz.creditos_voz(e.voz, ep.voz, e.tono) for e in ep.escenas) if ep.voz.motor == "elevenlabs" else 0
        c_son, nuevos = costo_sonidos(ep)
        if (c_voz or c_son) and not gastar:
            raise voz.FaltaConfirmar(
                f"Esto gastaría ~{c_voz + c_son} créditos de ElevenLabs (voz {c_voz}, sonidos nuevos {c_son}: "
                f"{', '.join(p[:28] for _, p, _ in nuevos) or 'ninguno'}). Lo ya guardado no se cobra.\n"
                "Para confirmar agrega --si; para un borrador gratis usa --voz kokoro.")
    ancho, alto, resol = FORMATOS[ep.formato]
    lugares = Lugares(ep.region, ep.lugares)

    _paso(1, 5, "Relieve y textura")
    # el relieve cubre todo lo que ve la cámara (si no, quedan franjas oscuras arriba y abajo)
    camaras = [(*lugares.punto(e.camara.ir_a), e.camara.altura, e.camara.inclinacion, e.camara.rumbo)
               for e in ep.escenas if e.camara]
    foco_y = FOCO_Y if alto > ancho else 0.0
    zona = encuadre.region_visible(ep.region, camaras, ancho / alto, foco_y)
    # más resolución cuanto más grande la zona, para no perder detalle en los acercamientos
    crece = ((zona[2] - zona[0]) * (zona[3] - zona[1]) / ((ep.region[2] - ep.region[0]) * (ep.region[3] - ep.region[1]))) ** 0.5
    lado = lambda base, tope: int(min(tope, max(base, base * crece)) // 256 * 256)  # noqa: E731
    textura, rejilla, n_capas = lado(cal.textura, 8192), lado(cal.rejilla, 768), lado(cal.capas, 4096)
    print(f"      zona visible: {zona} (textura {textura}, rejilla {rejilla})")
    fuente = datos.blue_marble(hd=calidad == "maxima")
    info = terreno.preparar(zona, dat, textura, rejilla, fuente)
    _textura_globo(fuente, cal.globo, dat / "blue-marble.jpg")

    _paso(2, 5, "Formas y mapas")
    geoms = {k: capas.forma(f, lugares, zona) for k, f in ep.formas.items()}
    info["formas"] = capas.mascaras(geoms, zona, dat, n=n_capas)
    info["mapas"] = [capas.mapa_politico(k, a, zona, ep.colores, lugares, dat, n=n_capas) for k, a in ep.mapas.items()]

    _paso(3, 5, f"Voz ({ep.voz.motor})")
    if not audio and ep.voz.motor == "elevenlabs" and sum(voz.creditos_voz(e.voz, ep.voz, e.tono) for e in ep.escenas):
        ep.voz.motor = "estimar"   # vista previa: tiempos estimados, sin pagar voz
    voces = voz.generar(nombre, ep.escenas, ep.voz, RAIZ / "voz", gastar=gastar)

    _paso(4, 5, "Línea de tiempo")
    comp = compilar(ep, voces, lugares, {"region": zona, "rejilla": info["rejilla"], "formas": info["formas"],
                                          "mapas": [{"id": m["id"]} for m in info["mapas"]]}, (ancho, alto))
    comp.escena["foco_y"] = foco_y
    comp.escena["escala"] = cal.escala
    comp.escena["antialias"] = cal.antialias   # el MSAA cuesta ~35 % sin GPU
    (dat / "escena.json").write_text(json.dumps(comp.escena, ensure_ascii=False), encoding="utf-8")
    dur = comp.escena["duracion"]
    print(f"      duración: {dur:.1f} s, {len(ep.escenas)} escenas")
    for id_, t0, t1 in comp.tiempos:
        print(f"        {t0:6.1f}–{t1:6.1f}  {id_}")

    _paso(5, 5, "Audio")
    mezcla = None
    if audio:
        musica, vol_musica, efectos, ambientes = _sonidos_ia(ep, comp, dur)
        mezcla = mezclador.mezclar(dur, comp.voces, efectos, musica=musica, vol_musica=vol_musica,
                          ambientes=ambientes, salida=str(build / "mezcla.wav"))
    else:
        print("      (vista previa: sin audio)")

    # proyecto HyperFrames
    creditos = " · ".join(["AWS Terrain Tiles", "NASA Blue Marble", "Natural Earth"]
                          + (["historical-basemaps"] if any(m["anio"] for m in info["mapas"]) else []))
    html = (MOTOR / "plantilla.html").read_text(encoding="utf-8")
    for k, v in {"ANCHO": ancho, "ALTO": alto, "RESOLUCION": resol, "DURACION": f"{dur:.3f}", "CREDITO": creditos}.items():
        html = html.replace("{{" + k + "}}", str(v))
    (build / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(MOTOR / "motor.js", build / "motor.js")
    (build / "lib").mkdir()
    libs = MOTOR / "node_modules" / "three" / "build"
    if not libs.exists():
        raise RuntimeError("Falta three.js: ejecuta 'npm install' dentro de motor3d/")
    for f in ("three.module.js", "three.core.js"):
        shutil.copy(libs / f, build / "lib" / f)
    (build / "fuentes").mkdir()
    for f in ("Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf"):
        shutil.copy(RAIZ / "fuentes" / f, build / "fuentes" / f)
    (build / "meta.json").write_text(json.dumps({"id": nombre, "name": ep.titulo}), encoding="utf-8")
    return build, {"episodio": ep, "nombre": nombre, "duracion": dur, "mezcla": mezcla, "calidad": cal,
                   "resolucion": resol + ("-4k" if cal.escala == 2 else "")}


def _musica_pedida(ep, nombre: str) -> tuple[str, float]:
    from . import kit
    return kit.musica(nombre) if nombre in kit.MUSICA else (nombre, ep.musica.segundos or kit.SEGUNDOS_MUSICA)


def planear_sonidos(ep) -> list[tuple[str, str, float | None]]:
    """Todo lo que el episodio pide a ElevenLabs aparte de la voz: [(tipo, pedido, duración)], sin repetir."""
    from . import kit
    from .modelo import MusicaIA
    plan = []
    if isinstance(ep.musica, MusicaIA):
        plan += [("musica", *_musica_pedida(ep, m)) for m in [ep.musica.pedido] + [e.musica for e in ep.escenas if e.musica]]
    for e in ep.escenas:
        plan += [("efecto", ef.pedido, ef.duracion) for ef in e.efectos if not isinstance(ef, str)]
        if e.ambiente:
            plan.append(("efecto", *kit.ambiente(e.ambiente)))
    return list(dict.fromkeys(plan))


def costo_sonidos(ep) -> tuple[int, list]:
    """Créditos de lo que falta en la biblioteca (lo guardado no se cobra) y la lista de lo nuevo."""
    from . import elevenlabs
    nuevos = [(t, p, d) for t, p, d in planear_sonidos(ep)
              if not (elevenlabs.ruta_musica(p, d) if t == "musica" else elevenlabs.ruta_efecto(p, d)).exists()]
    costo = sum(elevenlabs.costo_musica(d) if t == "musica" else elevenlabs.costo_efecto(d) for t, _, d in nuevos)
    return costo, nuevos


def _sonidos_ia(ep, comp, dur):
    """Resuelve música, efectos y ambientes a archivos (de la biblioteca o generados con ElevenLabs)."""
    from .modelo import MusicaIA
    hay_clave = bool(os.environ.get("ELEVENLABS_API_KEY"))
    if not hay_clave and (isinstance(ep.musica, MusicaIA) or comp.ambientes or any(not isinstance(n, str) for n, *_ in comp.efectos)):
        print("  aviso: sin ELEVENLABS_API_KEY se omiten la música, los efectos y los ambientes generados")
    from . import elevenlabs
    from . import kit
    musica, vol = None, 0.22
    if isinstance(ep.musica, MusicaIA) and hay_clave:
        vol = ep.musica.vol
        tramos = [(ep.musica.pedido, 0.0)] + list(comp.musicas)
        musica = [(str(elevenlabs.musica(*_musica_pedida(ep, m))), t) for m, t in tramos]
    elif ep.musica and isinstance(ep.musica, str) and Path(ep.musica).exists():
        musica = ep.musica
    efectos = []
    for n, t, g in comp.efectos:
        if isinstance(n, str):
            efectos.append((n, t, g))
        elif hay_clave:
            efectos.append((str(elevenlabs.efecto(n.pedido, n.duracion)), t, g))
    ambientes = []
    if hay_clave:
        for nombre, t0, t1 in comp.ambientes:
            ambientes.append((str(elevenlabs.efecto(*kit.ambiente(nombre))), t0, t1))
    return musica, vol, efectos, ambientes


def _textura_globo(fuente: Path, ancho: int, destino: Path):
    """Textura del globo al tamaño que aguantan las GPU (máx. 8192 px en la mayoría)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(fuente).convert("RGB")
    if im.width > ancho:
        im = im.resize((ancho, ancho // 2), Image.LANCZOS)
    im.save(destino, quality=92)


def fotogramas(build: Path, segundos: list[float], salida: Path) -> list[Path]:
    salida.mkdir(parents=True, exist_ok=True)
    subprocess.run(["node", str(MOTOR / "fotogramas.mjs"), str(build), str(salida), *map(str, segundos)], check=True)
    return sorted(salida.glob(f"{build.name}_t*.jpg"))


def renderizar(build: Path, info: dict, procesos: int | None = None) -> Path:
    salida = RAIZ / "salida"
    salida.mkdir(exist_ok=True)
    mudo = build / "video_mudo.mp4"
    env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "HYPERFRAMES_SKIP_SKILLS": "1"}
    procesos = procesos or max(1, min(4, os.cpu_count() or 1))
    cal = info["calidad"]
    cmd = ["npx", "--yes", HYPERFRAMES, "render", "-w", str(procesos), "-o", str(mudo), "-q", cal.hf_calidad,
           "--resolution", info["resolucion"], "--protocol-timeout", "900000"]
    if cal.crf is not None:
        cmd += ["--crf", str(cal.crf)]
    t0 = time.time()
    subprocess.run(cmd, cwd=build, env=env, check=True)
    print(f"      render: {time.time() - t0:.0f} s")
    final = salida / f"{info['nombre']}{'' if cal.nombre == 'normal' else '_' + cal.nombre}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mudo), "-i", info["mezcla"], "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "384k", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    descripcion(info, salida / f"{info['nombre']}_descripcion.txt")
    return final


def recortar(build: Path, info: dict, desde: float, hasta: float) -> None:
    """Convierte el build en una muestra de [desde, hasta] segundos (para revisar sin renderizar todo)."""
    hasta = min(hasta, info["duracion"])
    dur = hasta - desde
    esc = json.loads((build / "datos" / "escena.json").read_text(encoding="utf-8"))
    esc["desfase"] = desde
    (build / "datos" / "escena.json").write_text(json.dumps(esc, ensure_ascii=False), encoding="utf-8")
    html = (build / "index.html").read_text(encoding="utf-8")
    (build / "index.html").write_text(html.replace(f'data-duration="{info["duracion"]:.3f}"', f'data-duration="{dur:.3f}"'),
                                      encoding="utf-8")
    tramo = build / "mezcla_muestra.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(desde), "-t", str(dur), "-i", info["mezcla"], str(tramo)], check=True)
    info.update(mezcla=str(tramo), duracion=dur, nombre=f"{info['nombre']}_muestra_{desde:g}-{hasta:g}s")


def descripcion(info: dict, ruta: Path):
    ep = info["episodio"]
    p = ep.publicacion
    lineas = [p.titulo if p else ep.titulo, ""]
    if p:
        lineas += [p.descripcion.strip(), "", "Fuentes:"] + [f"- {f}" for f in p.fuentes] + [""]
    lineas += ["Créditos de datos: " + "; ".join(datos.CREDITOS.values()) + ".", "Fronteras aproximadas."]
    if ep.voz.motor in ("kokoro", "chatterbox"):
        lineas.append("Narración con voz sintética (marca 'contenido alterado o sintético' al subir).")
    if p and p.hashtags:
        lineas += ["", " ".join(p.hashtags)]
    lineas += ["", f"Duración: {info['duracion']:.0f} s"]
    ruta.write_text("\n".join(lineas), encoding="utf-8")
