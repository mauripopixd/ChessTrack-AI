"""Cómo habla el coach según lo que sabe el usuario: la notación (SAN) traducida a palabras."""

import chess
import pytest

from app.coach.lenguaje import adaptar, en_palabras, jugadas_sugeridas


def tras(*sans: str) -> chess.Board:
    b = chess.Board()
    for s in sans:
        b.push_san(s)
    return b


ITALIANA = ("e4", "e5", "Nf3", "Nc6", "Bc4", "d5")


@pytest.mark.parametrize(
    ("fen", "san", "esperado"),
    [
        (chess.STARTING_FEN, "Nf3", "el caballo de g1 va a f3"),
        ("rnbqkbnr/ppp1pppp/8/8/2pP4/8/PP2PPPP/RNBQKBNR w KQkq - 0 3", "e3", "el peón de e2 va a e3"),
        ("rnbqkbnr/ppp1pppp/8/3p4/2P5/8/PP1PPPPP/RNBQKBNR b KQkq - 0 2", "dxc4",
         "el peón de d5 se come el peón de c4"),
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "O-O-O", "enroque largo: el rey va a c1 y la torre a d1"),
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2", "exd6",
         "el peón de e5 se come al paso el peón de d5 y queda en d6"),
        ("8/4P1k1/8/8/8/8/8/4K3 w - - 0 1", "e8=Q", "el peón de e7 va a e8 y se convierte en dama"),
        ("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", "Ra8#", "la torre de a1 va a a8 y da jaque mate"),
    ],
)  # fmt: skip
def test_en_palabras(fen, san, esperado):
    b = chess.Board(fen)
    assert en_palabras(b, b.parse_san(san)) == esperado


def test_sin_notacion_las_jugadas_van_en_palabras():
    b = tras(*ITALIANA)
    t = adaptar("Ahora puedes jugar exd5, y **Nxe5** también es posible.", b, "none")
    assert t == (
        "Ahora puedes jugar «el peón de e4 se come el peón de d5», y "
        "**el caballo de f3 se come el peón de e5** también es posible."
    )


def test_basico_anade_las_palabras_entre_parentesis():
    t = adaptar("Juega exd5.", tras(*ITALIANA), "basic")
    assert t == "Juega exd5 (el peón de e4 se come el peón de d5)."


def test_avanzado_no_cambia_nada():
    texto = "Juega exd5 y luego Nxe5."
    assert adaptar(texto, tras(*ITALIANA), "advanced") == texto


def test_una_jugada_ya_hecha_se_traduce_con_su_posicion():
    # Bc4 ya se jugó: en la posición actual el alfil está en c4, pero la frase habla de entonces
    t = adaptar("Tu jugada Bc4 fue buena.", tras(*ITALIANA), "none")
    assert t == "Tu jugada «el alfil de f1 va a c4» fue buena."


def test_las_casillas_no_se_confunden_con_jugadas_de_peon():
    b = tras(*ITALIANA)
    assert adaptar("La casilla e4 está atacada y en d4 no hay nada.", b, "none") == (
        "La casilla e4 está atacada y en d4 no hay nada."
    )
    assert adaptar("Mejor era d3.", tras("e4", "e5", "Nf3", "Nc6"), "none") == (
        "Mejor era «el peón de d2 va a d3»."
    )


def test_una_linea_se_lee_como_secuencia():
    t = adaptar("La línea 1.e4 e5 2.Nf3 es clásica.", tras("e4", "e5", "Nf3"), "none")
    assert t == (
        "La línea «el peón de e2 va a e4»; después, «el peón de e7 va a e5»; después, "
        "«el caballo de g1 va a f3» es clásica."
    )


def test_una_jugada_que_no_encaja_se_traduce_sin_tablero():
    # Qxf7# después de una jugada hipotética de las blancas: no está en ninguna posición
    t = adaptar("Qh5 amenaza Qxf7#.", tras("e4", "e5", "Bc4", "Nc6"), "none")
    assert t == "«la dama de d1 va a h5» amenaza «la dama se come lo que hay en f7 y da jaque mate»."


# ---------------------------------------------------------------- jugadas que sugiere el coach


def sugeridas(texto: str, *sans: str) -> list[str]:
    return [m.uci() for m in jugadas_sugeridas(texto, tras(*sans))]


def test_sugerencias_en_orden_y_sin_repetir():
    abierta = ("e4", "e5", "Nf3", "Nc6")
    assert sugeridas("Puedes jugar Bc4 o Bb5; también d4. Insisto: Bc4.", *abierta) == [
        "f1c4",
        "f1b5",
        "d2d4",
    ]


def test_no_son_sugerencias_las_desaconsejadas_ni_las_casillas_ni_las_lineas():
    abierta = ("e4", "e5", "Nf3", "Nc6")
    assert sugeridas("Ahora Nxe5 pierde una pieza. Evita Ng5, juega d4.", *abierta) == ["d2d4"]
    assert sugeridas("La casilla d4 es clave.", *abierta) == []
    assert sugeridas("La línea Bc4 Bc5 c3 es la italiana.", *abierta) == ["f1c4"]  # solo la primera
    assert sugeridas("La teoría dice 3.Bb5.", *abierta) == []  # numerada: teoría, no sugerencia
    assert sugeridas("Juega Nf6.", *abierta) == []  # no es legal ahora


def test_como_mucho_cuatro():
    assert len(sugeridas("Opciones: Nf3, Nc3, e4, d4, c4.")) == 4


LISTA = (
    "Opciones:\n\n1. **Nc3** – el caballo de b1 va a c3. Bien.\n2. **d4** (el peón de d2 va a d4). Centro."
)


def test_lista_numerada_y_traduccion_que_ya_escribio_el_llm():
    # "2." es el punto de una lista, no la jugada 2; y la traducción del LLM no sale dos veces
    b = tras("e4", "Na6")
    assert adaptar(LISTA, b, "none") == (
        "Opciones:\n\n1. **el caballo de b1 va a c3**. Bien.\n2. **el peón de d2 va a d4**. Centro."
    )
    assert adaptar(LISTA, b, "basic") == (
        "Opciones:\n\n1. **Nc3 (el caballo de b1 va a c3)**. Bien.\n"
        "2. **d4 (el peón de d2 va a d4)**. Centro."
    )
    assert [m.uci() for m in jugadas_sugeridas(LISTA, b)] == ["b1c3", "d2d4"]


def test_sugerencias_escritas_ya_en_palabras():
    # El LLM a veces copia el estilo de sus respuestas anteriores (ya traducidas)
    texto = (
        "1. **el caballo de b1 va a c3** – espacio.\n2. **d4**. Centro.\n"
        "No hagas que el alfil de f1 se come el caballo de a6 todavía. Luego, enroque corto."
    )
    assert sugeridas(texto, "e4", "Na6") == ["b1c3", "d2d4"]  # sin enroque: aún no se puede
