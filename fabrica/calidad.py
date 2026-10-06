"""Niveles de calidad. 'maxima' = 4K nativo (el 3D se dibuja a 2160×3840, no se reescala)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Calidad:
    nombre: str
    escala: int            # 1 = 1080p, 2 = 4K (HyperFrames --resolution *-4k)
    antialias: bool
    hf_calidad: str        # draft | high | delivery
    crf: int | None        # None = el de HyperFrames
    textura: int           # lado de la textura de relieve (px)
    rejilla: int           # vértices por lado de la malla de relieve
    capas: int             # lado de máscaras y mapas políticos (px)
    globo: int             # ancho de la textura del globo (px)


CALIDADES = {
    "borrador": Calidad("borrador", 1, False, "draft", None, 2048, 256, 1024, 4096),
    "normal": Calidad("normal", 1, True, "high", None, 4096, 384, 2048, 4096),
    "maxima": Calidad("maxima", 2, True, "delivery", 12, 8192, 512, 4096, 8192),
}
