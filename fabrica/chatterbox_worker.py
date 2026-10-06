"""Proceso aparte que sintetiza con Chatterbox (vive en su propio entorno: modelos/venv-chatterbox).

Entrada (stdin, JSON): {"referencia": ruta|null, "items": [{"texto", "emocion", "cfg", "salida"}, ...]}
Escribe un WAV por item. El modelo se carga una sola vez para todo el episodio.
"""
import json
import sys

import soundfile as sf
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS


def main():
    pedido = json.load(sys.stdin)
    disp = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"chatterbox: cargando en {disp}...", file=sys.stderr, flush=True)
    m = ChatterboxMultilingualTTS.from_pretrained(device=disp)
    extra = {"audio_prompt_path": pedido["referencia"]} if pedido.get("referencia") else {}
    items = pedido["items"]
    for i, it in enumerate(items, 1):
        torch.manual_seed(7)   # misma frase + mismos ajustes = mismo audio
        wav = m.generate(it["texto"], language_id="es", exaggeration=it["emocion"], cfg_weight=it["cfg"], **extra)
        sf.write(it["salida"], wav.squeeze(0).cpu().numpy(), m.sr)
        print(f"chatterbox: {i}/{len(items)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
