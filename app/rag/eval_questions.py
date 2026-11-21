"""Preguntas de evaluación del RAG de aperturas, con la fuente que debería encontrarse.

Cada pregunta acepta varias secuencias de jugadas: un acierto es cualquier fragmento cuyas
jugadas EMPIECEN por una de ellas (una página más profunda de la misma apertura también
vale). Las 10 primeras son las del checkpoint de la Etapa 5A.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Pregunta:
    texto: str
    jugadas: tuple[str, ...]  # prefijos aceptados
    nombre: str | None = None  # o un nombre de Lichess que lo contenga (otros órdenes de jugadas)


PREGUNTAS = [
    # --- checkpoint (10)
    Pregunta("¿Cuál es la idea principal de la Defensa Siciliana?", ("1. e4 c5",)),
    Pregunta("¿Qué busca el negro con la Defensa Francesa?", ("1. e4 e6",)),
    Pregunta("¿Por qué la Defensa Caro-Kann se considera sólida?", ("1. e4 c6",)),
    Pregunta("¿Qué pasa en el Gambito de Dama si el negro acepta el peón?", ("1. d4 d5 2. c4 dxc4",)),
    Pregunta(
        "¿Qué jugadas definen la Variante Najdorf de la Siciliana?",
        ("1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6",),
    ),
    Pregunta(
        "¿Cuál es el plan de las blancas en la Apertura Española (Ruy López)?",
        ("1. e4 e5 2. Nf3 Nc6 3. Bb5",),
    ),
    Pregunta("¿Qué ofrece el blanco en el Gambito de Rey y por qué?", ("1. e4 e5 2. f4",)),
    Pregunta("¿Qué ideas tiene el negro en la Defensa India de Rey?", ("1. d4 Nf6 2. c4 g6",)),
    Pregunta("¿En qué consiste la Defensa Escandinava?", ("1. e4 d5",)),
    Pregunta("¿Por qué 1. Na3 se considera una mala primera jugada?", ("1. Na3",)),
    # --- resto
    Pregunta("¿Qué es la Apertura Inglesa?", ("1. c4",)),
    Pregunta("¿Qué es la Defensa Alekhine?", ("1. e4 Nf6",)),
    Pregunta("¿Qué es la Defensa Holandesa?", ("1. d4 f5",)),
    Pregunta("¿Qué es el Gambito Evans?", ("1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4",)),
    Pregunta("¿Qué es la Defensa Pirc?", ("1. e4 d6",)),
    Pregunta("¿Qué es el Gambito Budapest?", ("1. d4 Nf6 2. c4 e5",)),
    Pregunta("¿Qué es la Defensa Petrov o Rusa?", ("1. e4 e5 2. Nf3 Nf6",)),
    Pregunta(
        "¿Qué es el Ataque Fried Liver (Fegatello)?",
        ("1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7",),
    ),
    Pregunta(
        "¿Cuál es la idea del Sistema Londres?",
        ("1. d4 d5 2. Bf4", "1. d4 Nf6 2. Bf4"),
        nombre="London System",  # se llega por muchos órdenes de jugadas
    ),
    Pregunta("¿Qué es la Defensa Eslava?", ("1. d4 d5 2. c4 c6",)),
]

CHECKPOINT = PREGUNTAS[:10]


def acierta(moves: str, name: str | None, pregunta: Pregunta) -> bool:
    if pregunta.nombre and name and pregunta.nombre in name:
        return True
    return any(moves == p or moves.startswith(p + " ") for p in pregunta.jugadas)
