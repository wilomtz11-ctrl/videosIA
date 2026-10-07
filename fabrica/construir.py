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

from . import capas, datos, terreno, voz
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


def preparar(ruta_ep: Path, motor_voz: str | None = None, calidad: str = "normal") -> tuple[Path, dict]:
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
    ancho, alto, resol = FORMATOS[ep.formato]
    lugares = Lugares(ep.region, ep.lugares)

    _paso(1, 5, "Relieve y textura")
    fuente = datos.blue_marble(hd=calidad == "maxima")
    info = terreno.preparar(ep.region, dat, cal.textura, cal.rejilla, fuente)
    _textura_globo(fuente, cal.globo, dat / "blue-marble.jpg")

    _paso(2, 5, "Formas y mapas")
    geoms = {k: capas.forma(f, lugares, ep.region) for k, f in ep.formas.items()}
    info["formas"] = capas.mascaras(geoms, ep.region, dat, n=cal.capas)
    info["mapas"] = [capas.mapa_politico(k, a, ep.region, ep.colores, lugares, dat, n=cal.capas) for k, a in ep.mapas.items()]

    _paso(3, 5, f"Voz ({ep.voz.motor})")
    voces = voz.generar(nombre, ep.escenas, ep.voz, RAIZ / "voz")

    _paso(4, 5, "Línea de tiempo")
    comp = compilar(ep, voces, lugares, {"rejilla": info["rejilla"], "formas": info["formas"],
                                          "mapas": [{"id": m["id"]} for m in info["mapas"]]}, (ancho, alto))
    comp.escena["escala"] = cal.escala
    comp.escena["antialias"] = cal.antialias   # el MSAA cuesta ~35 % sin GPU
    (dat / "escena.json").write_text(json.dumps(comp.escena, ensure_ascii=False), encoding="utf-8")
    dur = comp.escena["duracion"]
    print(f"      duración: {dur:.1f} s, {len(ep.escenas)} escenas")
    for id_, t0, t1 in comp.tiempos:
        print(f"        {t0:6.1f}–{t1:6.1f}  {id_}")

    _paso(5, 5, "Audio")
    musica, vol_musica, efectos, ambientes = _sonidos_ia(ep, comp, dur)
    mezcla = mezclador.mezclar(dur, comp.voces, efectos, musica=musica, vol_musica=vol_musica,
                               ambientes=ambientes, salida=str(build / "mezcla.wav"))

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


def _sonidos_ia(ep, comp, dur):
    """Resuelve música, efectos y ambientes a archivos (de la biblioteca o generados con ElevenLabs)."""
    from .modelo import MusicaIA
    hay_clave = bool(os.environ.get("ELEVENLABS_API_KEY"))
    if not hay_clave and (isinstance(ep.musica, MusicaIA) or comp.ambientes or any(not isinstance(n, str) for n, *_ in comp.efectos)):
        print("  aviso: sin ELEVENLABS_API_KEY se omiten la música, los efectos y los ambientes generados")
    from . import elevenlabs
    musica, vol = None, 0.22
    if isinstance(ep.musica, MusicaIA):
        if hay_clave:
            musica, vol = str(elevenlabs.musica(ep.musica.pedido, ep.musica.segundos or min(dur, 90))), ep.musica.vol
    elif ep.musica and Path(ep.musica).exists():
        musica = ep.musica
    efectos = []
    for n, t, g in comp.efectos:
        if isinstance(n, str):
            efectos.append((n, t, g))
        elif hay_clave:
            efectos.append((str(elevenlabs.efecto(n.pedido, n.duracion)), t, g))
    ambientes = []
    if hay_clave:
        for pedido, t0, t1 in comp.ambientes:
            ambientes.append((str(elevenlabs.efecto(pedido, min(22.0, t1 - t0))), t0, t1))
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
