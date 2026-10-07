"""Kit de sonido reutilizable: se genera UNA vez con ElevenLabs y todos los episodios lo usan gratis.

En el guion se usan los nombres cortos:
    efectos: [golpe_grave, monedas]      ambiente: olas      musica: tension
Los pedidos están en inglés porque ElevenLabs da mejores resultados así.
"""
from __future__ import annotations

# nombre: (pedido, duración en s)
EFECTOS = {
    "golpe_grave": ("Deep cinematic boom hit with long reverb tail", 3),
    "whoosh": ("Fast cinematic whoosh transition", 1.5),
    "whoosh_grave": ("Deep cinematic whoosh transition with low rumble", 2.0),
    "subida": ("Cinematic tension riser building up to a hit", 4),
    "revelacion": ("Bright cinematic reveal hit with shimmer", 2),
    "error": ("Deep wrong answer buzzer, cinematic", 1.5),
    "tic_tac": ("Old clock ticking, close and dry", 4),
    "latido": ("Slow heartbeat thump, cinematic tension", 4),
    "monedas": ("Handful of old metal coins dropping and clinking on a wooden table", 2),
    "tambores_guerra": ("Distant war drums and cannon rumble, cinematic", 4),
    "canon": ("Single cannon shot with distant echo", 3),
    "espadas": ("Swords clashing in battle", 2),
    "multitud": ("Crowd murmuring in a 19th century town square", 6),
    "tren_vapor": ("Steam train whistle and chugging locomotive", 6),
    "maquina_escribir": ("Old typewriter typing then a bell ding", 3),
    "sello": ("Official rubber stamp hitting paper", 1),
    "papel": ("Old paper map unfolding", 2),
    "campana": ("Church bell tolling once, distant", 4),
    "barco": ("Old wooden ship creaking with sails flapping", 5),
    "mazo": ("Judge wooden gavel striking twice in a quiet courtroom", 1.5),
}

# ambientes de fondo (12 s; se repiten en bucle con fundido, así cuestan menos)
AMBIENTES = {
    "viento_desierto": ("Cold wind blowing over a high desert plateau", 12),
    "olas": ("Ocean waves crashing on a rocky coast", 12),
    "selva": ("Tropical rainforest ambience with birds and insects", 12),
    "ciudad": ("Busy modern city ambience, traffic and people", 12),
    "batalla": ("Distant 19th century battle ambience, cannons and muskets", 12),
    "lluvia": ("Steady rain with distant thunder", 12),
    "montana": ("High mountain wind with a distant eagle cry", 12),
    "puerto": ("Old harbor ambience, seagulls, water and creaking boats", 12),
}

# música por emoción (60 s, se repite en bucle; ~14 créditos/s)
MUSICA = {
    "intriga": "Mysterious cinematic documentary underscore, low strings and soft pulsing synth, building suspense",
    "tension": "Tense cinematic underscore, driving low percussion, staccato strings, rising danger",
    "epico": "Epic orchestral documentary theme, big drums, brass and choir pads, triumphant",
    "emotivo": "Emotional cinematic piano and strings, hopeful and reflective",
    "descubrimiento": "Curious upbeat documentary underscore, light plucked strings and marimba, sense of discovery",
}
SEGUNDOS_MUSICA = 60


def efecto(nombre: str) -> tuple[str, float] | None:
    return EFECTOS.get(nombre)


def ambiente(nombre: str) -> tuple[str, float]:
    """Nombre del kit o pedido libre (se genera a 12 s y se repite)."""
    return AMBIENTES.get(nombre, (nombre, 12))


def musica(nombre: str) -> tuple[str, float]:
    return MUSICA.get(nombre, nombre), SEGUNDOS_MUSICA


def costo_estimado() -> int:
    from .elevenlabs import costo_efecto, costo_musica
    return (sum(costo_efecto(d) for _, d in EFECTOS.values()) + sum(costo_efecto(d) for _, d in AMBIENTES.values())
            + len(MUSICA) * costo_musica(SEGUNDOS_MUSICA))


def generar_todo() -> None:
    """Genera lo que falte del kit (lo que ya está en biblioteca/ no se vuelve a pagar)."""
    from . import elevenlabs
    for pedido, dur in EFECTOS.values():
        elevenlabs.efecto(pedido, dur)
    for pedido, dur in AMBIENTES.values():
        elevenlabs.efecto(pedido, dur)
    for pedido in MUSICA.values():
        elevenlabs.musica(pedido, SEGUNDOS_MUSICA)
