"""Construye un episodio: voz -> línea de tiempo -> audio -> video MP4 + descripción.

Ejemplos:
  python construir.py episodios/bolivia_mar.json --voz estimar          # vista previa rápida, sin voz
  python construir.py episodios/bolivia_mar.json --voz kokoro           # voz gratis en CPU
  python construir.py episodios/bolivia_mar.json --voz archivos         # tus WAV (grabados o de Colab)
  python construir.py episodios/bolivia_mar.json --fotogramas 1 12 40   # solo PNG de esos segundos
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

from videosia import audio, voz
from videosia.linea_tiempo import LineaTiempo
from videosia.render import Escenario

RAIZ = Path(__file__).resolve().parent


def descripcion(ep, lt, ruta, motor):
    d = ep.get("publicacion", {})
    lineas = [d.get("titulo", ep["titulo"]), "", d.get("descripcion", "").strip(), ""]
    if d.get("fuentes"):
        lineas.append("Fuentes:")
        lineas += [f"- {f}" for f in d["fuentes"]]
        lineas.append("")
    lineas.append("Mapas: historical-basemaps (A. Ourednik, GPL-3.0). Fronteras aproximadas.")
    if motor in ("kokoro", "chatterbox"):
        lineas.append("Narración con voz sintética. (Marca 'contenido alterado o sintético' al subir.)")
    lineas += ["", " ".join(d.get("hashtags", [])), "", f"Duración: {lt.duracion:.1f} s"]
    Path(ruta).write_text("\n".join(lineas), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodio")
    ap.add_argument("--voz", default="estimar", choices=["estimar", "archivos", "kokoro", "chatterbox"])
    ap.add_argument("--voz-nombre", default=None, help="kokoro: em_alex, ef_dora, em_santa")
    ap.add_argument("--referencia", default=None, help="chatterbox: WAV de 10-30 s de tu voz para clonarla")
    ap.add_argument("--formato", default="vertical", choices=["vertical", "horizontal"])
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fotogramas", type=float, nargs="*", help="exporta solo PNG de estos segundos")
    ap.add_argument("--musica", default=None, help="archivo de música (mp3/wav). Sobrescribe el del episodio")
    args = ap.parse_args()

    ep = json.load(open(args.episodio, encoding="utf-8"))
    nombre = Path(args.episodio).stem
    salida = RAIZ / "salida"
    salida.mkdir(exist_ok=True)

    opciones = dict(ep.get("voz", {}).get(args.voz, {}))
    if args.voz_nombre:
        opciones["voz"] = args.voz_nombre
    if args.referencia:
        opciones["referencia"] = args.referencia
    print(f"[1/4] Voz ({args.voz})")
    voces = voz.generar(nombre, ep["escenas"], args.voz, opciones, RAIZ / "voz")

    lt = LineaTiempo(ep, voces)
    print(f"      duración total: {lt.duracion:.1f} s ({len(lt.escenas)} escenas)")
    print("[2/4] Preparando mapas")
    esc = Escenario(ep, args.formato)

    sufijo = "" if args.formato == "vertical" else "_horizontal"
    if args.fotogramas is not None:
        import skia
        for s in args.fotogramas:
            img = esc.fotograma(lt.estado(min(s, lt.duracion - 0.01)))
            ruta = salida / f"{nombre}{sufijo}_t{s:05.1f}.png"
            skia.Image.fromarray(img).save(str(ruta), skia.kPNG)
            print("      ", ruta)
        return

    print("[3/4] Audio")
    musica = args.musica or ep.get("musica")
    if musica and not Path(musica).exists():
        print(f"      (no encontré la música {musica}; sigo sin música)")
        musica = None
    mezcla = audio.mezclar(lt.duracion, lt.voces, lt.efectos, musica=musica, salida=str(salida / f"{nombre}_mezcla.wav"))

    print("[4/4] Video")
    mp4 = salida / f"{nombre}{sufijo}.mp4"
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{esc.W}x{esc.H}",
        "-r", str(args.fps), "-i", "-", "-i", mezcla, "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-shortest", str(mp4)], stdin=subprocess.PIPE)
    n = int(lt.duracion * args.fps)
    t0 = time.time()
    for i in range(n):
        ff.stdin.write(esc.fotograma(lt.estado(i / args.fps)).tobytes())
        if i % (args.fps * 10) == 0:
            print(f"      {i / args.fps:5.1f} s / {lt.duracion:.1f} s  ({time.time() - t0:.0f} s transcurridos)")
    ff.stdin.close()
    ff.wait()
    descripcion(ep, lt, salida / f"{nombre}_descripcion.txt", args.voz)
    print(f"Listo: {mp4}")


if __name__ == "__main__":
    main()
