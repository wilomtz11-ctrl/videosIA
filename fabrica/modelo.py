"""Esquema del guion de un episodio (YAML). Pydantic valida todo antes de gastar tiempo en renderizar.

Un episodio mínimo:

    titulo: ¿Por qué Bolivia no tiene mar?
    escenas:
      - voz: Bolivia tiene armada... pero no tiene mar.
        camara: {ir_a: Bolivia, altura: pais}
"""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Alturas de cámara con nombre (radios terrestres sobre la superficie)
ALTURAS = {"espacio": 3.2, "globo": 2.4, "continente": 1.5, "pais": 0.8, "region": 0.38, "cerca": 0.18, "muy_cerca": 0.1}
COLORES = {
    "amarillo": "#F4D35E", "rojo": "#D7263D", "azul": "#4CC9F0", "verde": "#57CC99", "blanco": "#FFFFFF",
    "naranja": "#F79256", "morado": "#B79CD9", "celeste": "#9BE7FF",
}
MAX_FORMAS = 8


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _vacios(cls, datos):
        """Una sección vacía en el YAML (solo comentarios) vale como si no estuviera."""
        return {k: v for k, v in datos.items() if v is not None} if isinstance(datos, dict) else datos


Punto = Union[str, tuple[float, float]]   # nombre ("Calama", "Bolivia") o [lon, lat]


def color_hex(v: str) -> str:
    v = COLORES.get(v, v)
    if not (isinstance(v, str) and v.startswith("#") and len(v) == 7):
        raise ValueError(f"color no válido: {v!r} (usa #RRGGBB o uno de {sorted(COLORES)})")
    return v


class Camara(Estricto):
    ir_a: Punto
    altura: Union[float, str] = Field("pais", validate_default=True)
    inclinacion: float | None = Field(None, ge=0, le=75, description="0 = vista cenital; 60 = vista oblicua")
    rumbo: float = Field(0, description="hacia dónde mira la cámara, en grados desde el norte")
    duracion_movimiento: float = Field(1.6, gt=0, le=6)

    @field_validator("altura")
    @classmethod
    def _altura(cls, v):
        if isinstance(v, str):
            if v not in ALTURAS:
                raise ValueError(f"altura '{v}' no existe; usa un número o una de {list(ALTURAS)}")
            return ALTURAS[v]
        if not 0.04 <= v <= 4:
            raise ValueError("altura fuera de rango (0.04 a 4)")
        return v

    @model_validator(mode="after")
    def _inclinacion(self):
        if self.inclinacion is None:   # cuanto más cerca, más oblicua (se luce el relieve)
            self.inclinacion = 0 if self.altura >= 0.8 else (35 if self.altura >= 0.3 else 55)
        return self


class Titular(Estricto):
    texto: str = Field(min_length=1, max_length=70)
    estilo: Literal["alerta", "dato", "nota"] = "nota"
    retraso: float = Field(0.15, ge=0)


class Etiqueta(Estricto):
    texto: str | None = None
    en: Punto | None = None
    tam: int | None = Field(None, ge=18, le=96)
    estilo: Literal["pais", "punto", "agua"] | None = None


class Resalte(Estricto):
    forma: str
    color: str = "amarillo"
    retraso: float = Field(0.4, ge=0)
    _c = field_validator("color")(color_hex)


class Pintura(Estricto):
    forma: str
    color: str
    retraso: float = Field(0.6, ge=0)
    duracion: float = Field(1.2, gt=0)
    _c = field_validator("color")(color_hex)


class Flecha(Estricto):
    de: Punto
    a: Punto
    color: str = "rojo"
    retraso: float = Field(0.5, ge=0)
    duracion: float = Field(1.4, gt=0)
    _c = field_validator("color")(color_hex)


class Anillo(Estricto):
    en: Punto
    color: str = "amarillo"
    retraso: float = Field(0.4, ge=0)
    _c = field_validator("color")(color_hex)


class EfectoIA(Estricto):
    """Efecto de sonido generado con ElevenLabs y guardado en biblioteca/ (se reutiliza)."""
    pedido: str = Field(min_length=3, description="qué debe sonar (en inglés da mejores resultados)")
    retraso: float = Field(0.1, ge=0)
    vol: float = Field(0.8, ge=0, le=2)
    duracion: float | None = Field(None, gt=0, le=22)


class MusicaIA(Estricto):
    pedido: str = Field(min_length=3, description="emoción del kit (intriga, tension...) o estilo libre en inglés")
    vol: float = Field(0.18, ge=0, le=1)
    segundos: float | None = Field(None, description="largo a generar; si el video es más largo, se repite en bucle")


EFECTOS_INTERNOS = ("impacto", "whoosh", "pop")
TONOS = {   # tono en español -> etiqueta de ElevenLabs v3
    "misterio": "mysterious", "intriga": "intrigued", "tension": "tense", "tensión": "tense", "asombro": "amazed",
    "dramatico": "dramatic", "dramático": "dramatic", "emocion": "excited", "emoción": "excited", "serio": "serious",
    "susurro": "whispers", "curioso": "curious", "triste": "sad", "solemne": "solemn", "epico": "epic", "épico": "epic",
}


class Escena(Estricto):
    id: str | None = None
    voz: str = Field(min_length=3, description="lo que dice la narración; marca el ritmo de la escena")
    camara: Camara | None = None
    mapa: str | None = Field(None, description="año del mapa político (clave de 'mapas'); None = el de la escena anterior")
    anio: Union[int, str, None] = None
    titular: Union[Titular, str, None] = None
    etiquetas: list[Union[str, Etiqueta]] = []
    resaltar: list[Union[str, Resalte]] = []
    pintar: list[Pintura] = []
    flechas: list[Flecha] = []
    anillos: list[Union[str, Anillo]] = []
    efectos: list[Union[str, EfectoIA]] = Field([], description="impacto | whoosh | pop, o un efecto a medida: texto o {pedido, retraso, vol}")
    ambiente: str | None = Field(None, description="sonido de fondo de la escena (ElevenLabs), p. ej. 'desert wind'")
    tono: str | None = Field(None, description="elevenlabs: intención de la voz (misterio, tension, asombro, dramatico, serio...)")
    golpes: list[str] = Field([], description="frases de la narración que aparecen en grande cuando se dicen ('diez centavos')")
    musica: str | None = Field(None, description="cambia la música desde esta escena: emoción del kit (intriga, tension, epico, emotivo, descubrimiento)")
    pausa: float = Field(0.35, ge=0, le=3, description="silencio al final de la escena")
    emocion: float | None = Field(None, ge=0.25, le=1.5, description="chatterbox: intensidad de esta escena (si no, la del episodio)")

    @field_validator("titular")
    @classmethod
    def _titular(cls, v):
        return Titular(texto=v) if isinstance(v, str) else v

    @field_validator("etiquetas")
    @classmethod
    def _etiquetas(cls, v):
        return [Etiqueta(en=x) if isinstance(x, str) else x for x in v]

    @field_validator("resaltar")
    @classmethod
    def _resaltar(cls, v):
        return [Resalte(forma=x) if isinstance(x, str) else x for x in v]

    @field_validator("efectos")
    @classmethod
    def _efectos(cls, v):
        from . import kit
        out = []
        for x in v:
            if isinstance(x, EfectoIA) or x in EFECTOS_INTERNOS:
                out.append(x)
            elif kit.efecto(x):                      # nombre del kit de sonido
                pedido, dur = kit.efecto(x)
                out.append(EfectoIA(pedido=pedido, duracion=dur))
            else:
                out.append(EfectoIA(pedido=x))
        return out

    @field_validator("anillos")
    @classmethod
    def _anillos(cls, v):
        return [Anillo(en=x) if isinstance(x, str) else x for x in v]


class Forma(Estricto):
    """Zona que se puede resaltar o pintar. Ejemplos:
    {pais: Bolivia}                                 país actual (Natural Earth)
    {pais: Bolivia, anio: 1878}                     país en un año histórico (historical-basemaps)
    {op: interseccion, a: "1878:Bolivia", b: "2010:Chile", filtro: [lon0, lat0, lon1, lat1]}
    """
    pais: str | None = None
    anio: int | None = None
    op: Literal["interseccion", "diferencia", "union"] | None = None
    a: str | None = None
    b: str | None = None
    filtro: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def _uno(self):
        if bool(self.pais) == bool(self.op):
            raise ValueError("una forma necesita 'pais' o bien 'op' + 'a' + 'b'")
        if self.op and not (self.a and self.b):
            raise ValueError("una operación necesita 'a' y 'b'")
        return self


class Voz(Estricto):
    motor: Literal["kokoro", "chatterbox", "elevenlabs", "archivos", "estimar"] = "kokoro"
    voz: str = "em_alex"                                   # kokoro: nombre de voz; elevenlabs: id de la voz
    velocidad: float = Field(1.05, ge=0.7, le=1.4)         # solo kokoro
    referencia: str | None = Field(None, description="chatterbox: WAV de 10-30 s de la voz a clonar (por defecto, una voz en español)")
    emocion: float = Field(0.75, ge=0.25, le=1.5, description="chatterbox: 0.5 neutral, 0.75 intensa, 1.0 dramática")
    cfg: float = Field(0.35, ge=0, le=1, description="chatterbox: más bajo = ritmo más pausado")
    modelo: str = Field("eleven_v3", description="elevenlabs: eleven_v3 (más expresivo) o eleven_multilingual_v2")
    estabilidad: float = Field(0.4, ge=0, le=1, description="elevenlabs: más bajo = más emoción y variación")
    estilo: float = Field(0.3, ge=0, le=1, description="elevenlabs: exageración del estilo de la voz")


class Publicacion(Estricto):
    titulo: str
    descripcion: str = ""
    fuentes: list[str] = Field(min_length=1)
    hashtags: list[str] = []


class Episodio(Estricto):
    titulo: str
    formato: Literal["vertical", "horizontal"] = "vertical"
    region: tuple[float, float, float, float] = Field(description="lon0, lat0, lon1, lat1 de la zona con relieve en alta resolución")
    voz: Voz = Voz()
    musica: Union[str, MusicaIA, None] = Field(None, description="archivo de música, o {pedido} para generarla con ElevenLabs")
    exageracion: float = Field(5.0, ge=1, le=15, description="exageración vertical del relieve")
    mapas: dict[str, int] = Field(default_factory=lambda: {"hoy": 0}, description="clave -> año (0 = actual, Natural Earth)")
    colores: dict[str, str] = {}
    formas: dict[str, Forma] = {}
    lugares: dict[str, tuple[float, float]] = {}
    escenas: list[Escena] = Field(min_length=1)
    publicacion: Publicacion | None = None

    @field_validator("colores")
    @classmethod
    def _colores(cls, v):
        return {k: color_hex(c) for k, c in v.items()}

    @model_validator(mode="after")
    def _coherencia(self):
        if len(self.formas) > MAX_FORMAS:
            raise ValueError(f"máximo {MAX_FORMAS} formas por episodio (hay {len(self.formas)})")
        lon0, lat0, lon1, lat1 = self.region
        if not (lon0 < lon1 and lat0 < lat1):
            raise ValueError("region debe ser [lon0, lat0, lon1, lat1] con lon0<lon1 y lat0<lat1")
        if self.escenas[0].camara is None:
            raise ValueError("la primera escena necesita 'camara'")
        if self.escenas[0].mapa is None:
            self.escenas[0].mapa = next(iter(self.mapas))
        for i, e in enumerate(self.escenas):
            e.id = e.id or f"escena_{i + 1:02d}"
            if e.mapa is not None and e.mapa not in self.mapas:
                raise ValueError(f"escena '{e.id}': el mapa '{e.mapa}' no está en 'mapas' {list(self.mapas)}")
            usadas = [r.forma for r in e.resaltar] + [p.forma for p in e.pintar]
            for f in usadas:
                if f not in self.formas:
                    raise ValueError(f"escena '{e.id}': la forma '{f}' no está definida en 'formas'")
        ids = [e.id for e in self.escenas]
        if len(set(ids)) != len(ids):
            raise ValueError("hay escenas con el mismo id")
        return self
