"""Del corpus a fragmentos: jugadas desde el título, limpieza, troceo y cabeceras."""

import json

import pytest

from app.rag.corpus import (
    MAX_CARACTERES,
    build_chunks,
    limpiar,
    moves_from_title,
    trocear,
)
from app.rag.eval_questions import PREGUNTAS, Pregunta, acierta


@pytest.mark.parametrize(
    ("titulo", "jugadas"),
    [
        ("Chess Opening Theory/1. e4", "1. e4"),
        ("Chess Opening Theory/1. e4/1...c5", "1. e4 c5"),  # negras: no "1. ..c5"
        ("Chess Opening Theory/1. e4/1...c5/2. Nf3/2...d6", "1. e4 c5 2. Nf3 d6"),
        ("Chess Opening Theory/1. d4/1...Nf6/2. c4/2...g6", "1. d4 Nf6 2. c4 g6"),
        ("Chess Opening Theory", ""),
    ],
)
def test_jugadas_desde_el_titulo(titulo, jugadas):
    assert moves_from_title(titulo) == jugadas


def test_limpiar_corta_tablas_y_bibliografia():
    texto = "Idea del peón.\n\nPlan con d5.\n\n Theory table\n\n1. e4 c5\n\nReferences\nNCO 1999"
    assert limpiar(texto) == "Idea del peón.\n\nPlan con d5."


@pytest.mark.parametrize("titulo", ["Theory table", " Theory table ", "== References ==", "See also"])
def test_limpiar_reconoce_variantes_del_titulo(titulo):
    assert limpiar(f"Teoría útil.\n\n{titulo}\nbasura") == "Teoría útil."


def test_limpiar_no_corta_frases_que_solo_mencionan_la_palabra():
    texto = "Theory tables are a way of listing variations."
    assert limpiar(texto) == texto


def test_trocear_respeta_el_maximo_y_no_pierde_texto():
    parrafos = [f"Párrafo {i}. " + "x" * 300 for i in range(10)]
    trozos = trocear("\n\n".join(parrafos))
    assert all(len(t) <= MAX_CARACTERES for t in trozos)
    assert "".join(trozos).count("Párrafo") == 10


def test_trocear_parte_bloques_gigantes_sin_puntos():
    tabla = "\n".join(f"fila {i} " + "y" * 40 for i in range(200))  # sin párrafos ni puntos
    trozos = trocear(tabla)
    assert len(trozos) > 1 and all(len(t) <= MAX_CARACTERES for t in trozos)


def test_trocear_no_parte_un_parrafo_que_cabe():
    assert trocear("Una frase. Otra frase.") == ["Una frase. Otra frase."]


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "lichess").mkdir()
    (tmp_path / "lichess" / "b.tsv").write_text(
        "eco\tname\tpgn\nB20\tSicilian Defense\t1. e4 c5\n"
        "B90\tSicilian Defense: Najdorf Variation\t1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6\n",
        encoding="utf-8",
    )
    paginas = [
        {
            "title": "Chess Opening Theory/1. e4/1...c5",
            "url": "https://w/sic",
            "text": "Black fights for d4. " * 20,
        },
        {
            "title": "Chess Opening Theory/1. e4/1...c5/2. Nf3",
            "url": "https://w/nf3",
            "text": "Main line. " * 30,
        },
        {
            "title": "Chess Opening Theory/1. h4",
            "url": "https://w/h4",
            "text": "corto",
        },  # esbozo: se descarta
    ]
    (tmp_path / "wikibooks.jsonl").write_text("\n".join(json.dumps(p) for p in paginas), encoding="utf-8")
    return tmp_path


def test_build_chunks(corpus):
    chunks = build_chunks(corpus)
    wb = [c for c in chunks if c.source == "wikibooks"]
    li = [c for c in chunks if c.source == "lichess"]
    assert {c.url for c in wb} == {"https://w/sic", "https://w/nf3"}  # el esbozo no entra
    assert len(li) == 2 and all(c.license == "CC0" for c in li)
    sic = next(c for c in wb if c.url == "https://w/sic")
    assert sic.text.startswith("Sicilian Defense (B20) · 1. e4 c5\n\n")
    assert sic.license == "CC BY-SA 4.0" and sic.title == "1. e4/1...c5"
    # 2. Nf3 no está en el catálogo: hereda el nombre de la secuencia más larga que sí está.
    nf3 = next(c for c in wb if c.url == "https://w/nf3")
    assert (nf3.name, nf3.eco, nf3.moves) == ("Sicilian Defense", "B20", "1. e4 c5 2. Nf3")


def test_ids_unicos(corpus):
    ids = [c.id for c in build_chunks(corpus)]
    assert len(ids) == len(set(ids))


def test_acierto_por_prefijo_o_por_nombre():
    p = Pregunta("?", ("1. e4 c5",), nombre="Sicilian")
    assert acierta("1. e4 c5 2. Nf3", None, p)  # variante más profunda
    assert not acierta("1. e4 c6", None, p)
    assert not acierta("1. e4 c55", None, p)  # prefijo de texto, no de jugadas
    assert acierta("1. d4", "Sicilian Defense: transpuesta", p)


def test_hay_diez_preguntas_de_checkpoint():
    assert len(PREGUNTAS) >= 10 and len({p.texto for p in PREGUNTAS}) == len(PREGUNTAS)
