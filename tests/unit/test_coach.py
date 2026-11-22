"""Coach (Etapa 5B): partida, herramientas y grafo, con Stockfish real y un LLM falso.

El LLM falso devuelve respuestas guionizadas (texto o peticiones de herramienta) y guarda
lo que recibe: así se prueba el enrutado del grafo sin red y sin gastar el límite gratuito.
"""

import contextlib

import chess
import chess.engine
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.analysis import find_stockfish
from app.coach.game import CoachGame, GameOverError, IllegalMoveError
from app.coach.graph import MAX_RONDAS, build_graph
from app.coach.session import fuentes_citadas, normalizar_citas, play_turn
from app.coach.tools import colgando, describir, make_tools
from app.rag.hits import Hit
from tests.fakes import FakeLLM


def pide(herramienta: str, args: dict | None = None, n: int = 0) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": herramienta, "args": args or {}, "id": f"c{n}"}])


@pytest.fixture(scope="module")
def engine():
    ruta = find_stockfish()
    if ruta is None:
        pytest.skip("Stockfish no está instalado (ver README)")
    with chess.engine.SimpleEngine.popen_uci(ruta) as eng:
        eng.configure({"Threads": 1})
        yield eng


@pytest.fixture
def motor(engine):
    return lambda: contextlib.nullcontext(engine)


@pytest.fixture
def llm():
    return FakeLLM(respuestas=[], llamadas=[])


def factory(llm: FakeLLM):
    return lambda tools: llm


class FakeRetriever:
    def __init__(self):
        self.consultas = []

    def search(self, pregunta, k=5, source=None):
        self.consultas.append(pregunta)
        return [
            Hit(
                id="wb-1",
                text="The Italian Game begins 1.e4 e5 2.Nf3 Nc6 3.Bc4.",
                source="wikibooks",
                title="Italian Game",
                url="https://en.wikibooks.org/wiki/Chess_Opening_Theory/1._e4",
                moves="1. e4 e5 2. Nf3 Nc6 3. Bc4",
                name="Italian Game",
                eco="C50",
                license="CC BY-SA 4.0",
                score=0.9,
            )
        ]


# ---------------------------------------------------------------- partida (sin LLM)


TRAS_E4_D5 = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


def test_parse_move_acepta_san_y_uci():
    g = CoachGame()
    assert g.parse_move("e4") == chess.Move.from_uci("e2e4")
    assert g.parse_move("g1f3") == chess.Move.from_uci("g1f3")


@pytest.mark.parametrize("texto", ["e5", "Ke2", "zz", "e2e5"])
def test_parse_move_rechaza_ilegales_y_basura(texto):
    with pytest.raises(IllegalMoveError):
        CoachGame().parse_move(texto)


def test_parse_move_ambigua():
    g = CoachGame(board=chess.Board("4k3/8/8/8/8/8/8/1N1K1N2 w - - 0 1"))
    with pytest.raises(IllegalMoveError, match="ambigua"):
        g.parse_move("Nd2")


def test_jugada_y_respuesta_del_coach(engine):
    g = CoachGame(level=0)
    r = g.play_user_move("e4", engine, depth=8)
    assert (r.san, r.by, r.ply, r.label) == ("e4", "user", 1, "buena")
    c = g.play_coach_move(engine, think_time=0.05, depth=8)
    assert c.by == "coach" and c.ply == 2 and g.user_to_move
    assert g.last_user_report is r and g.last_coach_report is c


def test_coach_juega_primero_si_el_usuario_lleva_negras(engine):
    g = CoachGame(user_color=chess.BLACK, level=0)
    with pytest.raises(IllegalMoveError, match="turno"):
        g.play_user_move("e5", engine)
    assert g.play_coach_move(engine, think_time=0.05, depth=8).by == "coach"
    assert g.user_to_move


def test_partida_terminada(engine):
    g = CoachGame(board=chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"))
    assert g.result() == "0-1 (checkmate)"
    with pytest.raises(GameOverError):
        g.play_user_move("a3", engine)
    assert g.play_coach_move(engine) is None


# ---------------------------------------------------------------- herramientas


def test_describir_capturas_enroque_y_jaque():
    b = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    assert describir(b, b.parse_san("O-O")) == "O-O (enroque corto)"
    assert describir(b, b.parse_san("Bxf7+")) == "Bxf7+ (alfil de c4 captura peón en f7, jaque)"
    assert describir(b, b.parse_san("Nc3")) == "Nc3 (caballo de b1 va a c3)"


def test_colgando_detecta_pieza_sin_defensa_y_atacada_por_menos_valor():
    # Dama de d5 (defendida por la torre de d1) atacada por el peón de e6; caballo de a4 sin
    # defensa atacado por el alfil de c6. El peón de h2 está a salvo.
    b = chess.Board("4k3/8/2b1p3/3Q4/N7/8/7P/3RK3 w - - 0 1")
    peligro = colgando(b, chess.WHITE)
    assert "dama en d5 (la ataca algo de menos valor)" in peligro
    assert "caballo en a4 (sin defensa)" in peligro
    assert len(peligro) == 2


def test_herramientas_leen_la_partida_sin_que_el_llm_pase_fen(motor, engine):
    g = CoachGame(level=0)
    tools = {t.name: t for t in make_tools(g, motor)}
    assert all(not t.args for n, t in tools.items() if n != "buscar_teoria")  # sin argumentos
    assert "Todavía no has hecho" in tools["analizar_mi_ultima_jugada"].invoke({})
    g.play_user_move("e4", engine, depth=8)
    g.play_coach_move(engine, think_time=0.05, depth=8)
    estado = tools["estado_partida"].invoke({})
    assert "1. e4" in estado and "Turno: tuyo" in estado and "Última jugada (el coach)" in estado
    assert "Evaluación actual (Stockfish)" in estado
    assert "Mejores continuaciones" in tools["evaluar_posicion"].invoke({})
    assert "Tu jugada e4 (peón de e2 va a e4)" in tools["analizar_mi_ultima_jugada"].invoke({})
    assert "El coach jugó" in tools["explicar_jugada_del_coach"].invoke({})


def test_analisis_de_un_error_dice_que_queda_colgando(motor, engine):
    # 1.e4 d5 y 2.Qg4?? : la dama queda a tiro del alfil de c8
    g = CoachGame(board=chess.Board(TRAS_E4_D5))
    r = g.play_user_move("Qg4", engine, depth=10)
    assert r.label == "error_grave" and r.best_san != "Qg4"
    texto = {t.name: t for t in make_tools(g, motor)}["analizar_mi_ultima_jugada"].invoke({})
    assert "Tu jugada Qg4 (dama de d1 va a g4)" in texto and "error grave" in texto
    assert "Respuesta más fuerte del rival: Bxg4 (alfil de c8 captura dama en g4)" in texto
    assert "dama en g4 (sin defensa)" in texto


def test_buscar_teoria_sin_consulta_usa_las_jugadas(motor, engine):
    g = CoachGame(level=0)
    g.play_user_move("e4", engine, depth=6)
    ret = FakeRetriever()
    tools = {t.name: t for t in make_tools(g, motor, retriever=ret)}
    texto = tools["buscar_teoria"].invoke({})
    assert ret.consultas == ["opening 1. e4"]
    assert texto.startswith("[1] Italian Game — https://en.wikibooks.org/")
    assert "no está disponible" in {t.name: t for t in make_tools(g, motor)}["buscar_teoria"].invoke({})


# ---------------------------------------------------------------- grafo


def test_jugada_buena_no_llama_al_llm(motor, llm):
    g = CoachGame(level=0)
    r = play_turn(g, motor, move="e4", llm_factory=factory(llm))
    assert r.user_move.san == "e4" and r.coach_move is not None
    assert r.answer is None and llm.llamadas == []
    assert g.chat == []


def test_jugada_ilegal_no_mueve_nada(motor, llm):
    g = CoachGame(level=0)
    r = play_turn(g, motor, move="Ke2", llm_factory=factory(llm))
    assert r.error and "no es legal" in r.error
    assert r.user_move is None and r.coach_move is None and g.board.ply() == 0
    assert llm.llamadas == []


def test_error_del_usuario_dispara_comentario_con_el_analisis(motor, llm):
    g = CoachGame(board=chess.Board(TRAS_E4_D5))
    llm.respuestas = [AIMessage("Dejaste la dama en g4 a tiro del alfil.")]
    r = play_turn(g, motor, move="Qg4", llm_factory=factory(llm))  # la toma el alfil de c8
    assert r.user_move.label == "error_grave"
    assert r.answer.startswith("Dejaste")
    (mensajes,) = llm.llamadas
    sistema, pedido = mensajes[0].content, mensajes[-1].content
    assert "Estado actual de la partida" in sistema and "1. Qg4" in sistema
    assert "Tu jugada Qg4 (dama de d1 va a g4)" in pedido  # el análisis va en el mensaje
    assert f"El coach respondió de verdad: {r.coach_move.san}" in pedido
    assert g.chat == [("user", "¿Qué falló en mi jugada Qg4?"), ("coach", r.answer)]


def test_pregunta_con_herramienta_y_respuesta(motor, llm):
    g = CoachGame(level=0)
    play_turn(g, motor, move="e4", llm_factory=factory(llm))
    llm.respuestas = [pide("evaluar_posicion"), AIMessage("Vas un poco mejor.")]
    r = play_turn(g, motor, question="¿Voy ganando?", llm_factory=factory(llm))
    assert r.answer == "Vas un poco mejor." and r.user_move is None and r.coach_move is None
    segunda = llm.llamadas[1]
    assert isinstance(segunda[-1], ToolMessage) and "Mejores continuaciones" in segunda[-1].content
    assert g.chat[-2:] == [("user", "¿Voy ganando?"), ("coach", "Vas un poco mejor.")]


def test_el_historial_del_chat_llega_al_llm(motor, llm):
    g = CoachGame(level=0, chat=[("user", "hola"), ("coach", "¡hola!")])
    llm.respuestas = [AIMessage("ok")]
    play_turn(g, motor, question="¿y ahora?", llm_factory=factory(llm))
    contenidos = [m.content for m in llm.llamadas[0]]
    assert contenidos[1:4] == ["hola", "¡hola!", "¿y ahora?"]


def test_bucle_de_herramientas_se_corta(motor, llm):
    g = CoachGame(level=0)
    llm.respuestas = [pide("estado_partida", n=i) for i in range(10)]
    llm.respuestas.insert(MAX_RONDAS, AIMessage("cierre forzado"))
    r = play_turn(g, motor, question="¿qué hago?", llm_factory=factory(llm))
    assert r.answer == "cierre forzado"
    assert len(llm.llamadas) == MAX_RONDAS + 1
    assert "responde ahora" in llm.llamadas[-1][-1].content


def test_turno_es_jugada_o_pregunta(motor, llm):
    with pytest.raises(ValueError):
        play_turn(CoachGame(), motor, move="e4", question="¿?", llm_factory=factory(llm))
    with pytest.raises(ValueError):
        play_turn(CoachGame(), motor, llm_factory=factory(llm))


def test_build_graph_compila_sin_motor_ni_llm():
    grafo = build_graph(CoachGame(), motor=None, llm_factory=lambda tools: None)
    nodos = set(grafo.get_graph().nodes)
    assert {"jugada_usuario", "jugada_coach", "comentario", "pregunta", "coach", "herramientas"} <= nodos


def test_fuentes_citadas_solo_las_que_aparecen():
    busqueda = ToolMessage(
        "[1] A — https://a (CC0)\ntexto\n\n[2] B — https://b (CC BY-SA 4.0)\ntexto",
        tool_call_id="x",
        name="buscar_teoria",
    )
    assert fuentes_citadas("Según [2], …", [busqueda]) == ["[2] B — https://b (CC BY-SA 4.0)"]
    assert fuentes_citadas("Sin citas", [busqueda]) == []
    assert fuentes_citadas("[1]", []) == []


def test_mis_errores_ordena_del_peor_al_menos_grave(motor, engine):
    g = CoachGame(board=chess.Board(TRAS_E4_D5))
    tools = {t.name: t for t in make_tools(g, motor)}
    assert "Ninguna imprecisión" in tools["mis_errores"].invoke({})
    g.play_user_move("Qg4", engine, depth=8)
    texto = tools["mis_errores"].invoke({})
    assert "- Jugada 1. Qg4: error grave" in texto and "mejor era" in texto


def test_normalizar_citas_del_formato_nativo_de_gpt_oss():
    assert normalizar_citas("Es la Réti【1†source】 y【12†L3-L5】.") == "Es la Réti[1] y[12]."
    assert normalizar_citas("Sin cambios [2].") == "Sin cambios [2]."
