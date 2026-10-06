"""Línea de comandos.

  python -m fabrica validar episodios/bolivia_mar.yaml
  python -m fabrica previa episodios/bolivia_mar.yaml 1 8 20 45     # fotogramas sueltos (rápido)
  python -m fabrica video episodios/bolivia_mar.yaml                # video final
  python -m fabrica video episodios/bolivia_mar.yaml --borrador --voz estimar
"""
import argparse
import sys
from pathlib import Path

from pydantic import ValidationError


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fabrica", description="Fábrica de videos de mapas 3D")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validar", help="revisa el guion sin renderizar")
    v.add_argument("episodio", type=Path)
    p = sub.add_parser("previa", help="exporta fotogramas sueltos para revisar")
    p.add_argument("episodio", type=Path)
    p.add_argument("segundos", type=float, nargs="+")
    p.add_argument("--voz", choices=["kokoro", "chatterbox", "archivos", "estimar"])
    r = sub.add_parser("video", help="renderiza el video final")
    r.add_argument("episodio", type=Path)
    r.add_argument("--voz", choices=["kokoro", "chatterbox", "archivos", "estimar"])
    r.add_argument("--borrador", action="store_true", help="calidad baja, más rápido")
    r.add_argument("--procesos", type=int)
    a = ap.parse_args(argv)

    from . import construir
    try:
        if a.cmd == "validar":
            ep = construir.cargar(a.episodio)
            palabras = sum(len(e.voz.split()) for e in ep.escenas)
            print(f"OK: '{ep.titulo}', {len(ep.escenas)} escenas, {palabras} palabras (~{palabras / 2.6:.0f} s de voz)")
            return 0
        build, info = construir.preparar(a.episodio, a.voz, borrador=getattr(a, 'borrador', False))
        if a.cmd == "previa":
            for f in construir.fotogramas(build, a.segundos, construir.RAIZ / "salida" / "previa"):
                print("  ", f)
        else:
            print("  ", construir.renderizar(build, info, borrador=a.borrador, procesos=a.procesos))
        return 0
    except ValidationError as e:
        print("El guion tiene errores:\n" + "\n".join(f"  - {'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
        return 2


if __name__ == "__main__":
    sys.exit(main())
