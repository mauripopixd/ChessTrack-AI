"""Coach (Etapa 5B): partida, herramientas y grafo, con Stockfish real y un LLM falso.

El LLM falso devuelve respuestas guionizadas (texto o peticiones de herramienta) y guarda
lo que recibe: así se prueba el enrutado del grafo sin red y sin gastar el límite gratuito.
"""

import contextlib
import random

import chess
import chess.engine
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.analysis import find_stockfish
from app.coach.game import (
    ELO_POR_DEFECTO,
    CoachGame,
    GameOverError,
    IllegalMoveError,
    elegir_jugada_debil,
    temperatura,
)
from app.coach.graph import MAX_RONDAS, build_graph
from app.coach.session import fuentes_citadas, normalizar_citas, play_turn
from app.coach.tools import colgando, describir, make_tools, piezas_de
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
    assert all(
        not t.args for n, t in tools.items() if n not in ("buscar_teoria", "evaluar_jugada")
    )  # sin argumentos
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
    assert (
        "Tu jugada Qg4 (dama de d1 va a g4; ataca peón en g7, alfil en c8)" in texto
        and "error grave" in texto
    )
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
    assert "Tu jugada Qg4 (dama de d1 va a g4" in pedido  # el análisis va en el mensaje
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


POSICION_JAVIER = "r2q1rk1/4bpp1/p1np1n1p/1p2p3/3PP1b1/5NN1/PPB2PPP/R1BQR1K1 w - - 0 14"


def test_piezas_de_cada_bando_y_enroques_en_el_estado(motor):
    b = chess.Board(POSICION_JAVIER)
    assert piezas_de(b, chess.WHITE) == (
        "rey g1; dama d1; torres a1, e1; alfiles c1, c2; caballos f3, g3; peones a2, b2, f2, g2, h2, d4, e4"
    )
    estado = {t.name: t for t in make_tools(CoachGame(board=b), motor)}["estado_partida"].invoke({})
    assert "Tus piezas (blancas): rey g1" in estado and "Piezas del coach (negras): rey g8" in estado
    assert "Enroques que aún puedes hacer: ninguno" in estado
    inicial = {t.name: t for t in make_tools(CoachGame(), motor)}["estado_partida"].invoke({})
    assert "Enroques que aún puedes hacer: corto, largo" in inicial


def test_evaluar_jugada_candidata_sin_jugarla(motor):
    g = CoachGame(board=chess.Board(POSICION_JAVIER))
    evaluar = {t.name: t for t in make_tools(g, motor)}["evaluar_jugada"]
    texto = evaluar.invoke({"jugada": "d5"})
    assert texto.startswith("Si juegas d5 (peón de d4 va a d5; ataca caballo en c6)")
    assert "Casillas que cambian para tus piezas con d5:" in texto
    assert "Respuesta más fuerte del rival" in texto
    # d5 está a décimas de la mejor; según el ruido del motor sale como "mínima" o con la alternativa
    assert "Diferencia con la mejor jugada: mínima" in texto or "Lo mejor según Stockfish" in texto
    assert g.board.fen() == POSICION_JAVIER  # no la juega
    assert "no es una jugada legal" in evaluar.invoke({"jugada": "Ke5"})
    # Una jugada mala lo dice y da la alternativa
    malo = evaluar.invoke({"jugada": "Nh5"})  # el caballo de f3 a h5 lo pierde (Nxh5)
    assert "Lo mejor según Stockfish" in malo and "error" in malo


def test_balance_de_una_linea_distingue_cambio_ganancia_y_doblados():
    from app.coach.tools import balance_linea

    b = chess.Board()
    for j in ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]:
        b.push_san(j)
    cambio = balance_linea(b, ["Bxc6", "dxc6", "O-O"], chess.WHITE)
    assert cambio.startswith("cambio igualado") and "peones doblados del rival en la columna c" in cambio
    assert balance_linea(b, ["Ba4", "d6", "O-O"], chess.WHITE) == "sin capturas"
    # Las mismas capturas vistas desde negras: el que dobla peones es "tuyo"
    assert "peones doblados tuyos en la columna c" in balance_linea(b, ["Bxc6", "dxc6"], chess.BLACK)
    dama = chess.Board("rnbqkb1r/pppp1ppp/5n2/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 2 3")
    assert balance_linea(dama, ["Qh5", "Nxh5"], chess.WHITE).startswith("PIERDES material: -9")
    assert balance_linea(dama, ["Qh5", "Nxh5"], chess.BLACK).startswith("GANAS material: +9")


def test_evaluar_posicion_y_jugada_incluyen_el_balance(motor):
    g = CoachGame()
    for j in ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]:
        g.board.push_san(j)
    tools = {t.name: t for t in make_tools(g, motor)}
    assert "Balance:" in tools["evaluar_posicion"].invoke({})
    assert "Balance de tu jugada y esa continuación: cambio igualado" in tools["evaluar_jugada"].invoke(
        {"jugada": "Bxc6"}
    )


# ---------------------------------------------------------------- verificador


def test_jugadas_inventadas_detecta_piezas_que_no_pueden_mover():
    from app.coach.graph import jugadas_inventadas

    b = chess.Board()
    for j in [
        "e4",
        "c5",
        "Nf3",
        "d6",
        "Bc4",
        "e6",
        "O-O",
        "Nf6",
        "d3",
        "Nc6",
        "Nc3",
        "Rb8",
        "a4",
        "Be7",
        "Ne2",
        "a6",
        "Bb3",
        "b5",
    ]:
        b.push_san(j)
    # La respuesta real del coach a Javier: "Ne2 protege c3" (el caballo ya estaba en e2),
    # "Nd5" y "Nb1-c3" (no se pueden jugar); Ng3 sí es legal y Na5 viene en los datos.
    texto = "Una alternativa es **Ne2**, que prepara Nd5, o Nb1-c3. Tras Ng3 el negro juega Na5."
    # Nd5 no se marca: es legal para las negras (Nf6-d5) como respuesta
    assert jugadas_inventadas(texto, b, datos="... Na5 (caballo de c6 va a a5) ...") == ["Nb1", "Ne2"]
    assert jugadas_inventadas("Juega c3 y luego Bc2 o Ba2.", b, datos="") == []


def test_atacadas_por_dice_lo_que_ataca_la_pieza_movida():
    from app.coach.tools import atacadas_por

    b = chess.Board()
    for j in [
        "e4",
        "c5",
        "Nf3",
        "d6",
        "Bc4",
        "e6",
        "O-O",
        "Nf6",
        "d3",
        "Nc6",
        "Nc3",
        "Rb8",
        "a4",
        "Be7",
        "Ne2",
        "a6",
        "Bb3",
        "b5",
        "c3",
    ]:
        b.push_san(j)
    assert atacadas_por(b, b.parse_san("b4")) == ["peón en c3"]  # no el alfil de b3
    assert atacadas_por(b, b.parse_san("Na5")) == ["alfil en b3"]


def test_el_verificador_hace_reescribir_si_hay_jugadas_inventadas(motor, llm):
    g = CoachGame(level=0)
    llm.respuestas = [AIMessage("Juega Nb1-c3 y Nd5."), AIMessage("Desarrolla el caballo a c3 o f3.")]
    r = play_turn(g, motor, question="¿qué hago?", llm_factory=factory(llm))
    assert r.answer == "Desarrolla el caballo a c3 o f3."
    aviso = llm.llamadas[-1][-1].content
    # Desde la posición inicial ni Nb1 ni Nd5 son jugables (Nc3 sí, y no se marca)
    assert aviso.startswith("Revisión automática") and "Mencionas Nb1, Nd5:" in aviso


def test_el_verificador_no_toca_respuestas_correctas(motor, llm):
    g = CoachGame(level=0)
    llm.respuestas = [AIMessage("Puedes jugar Nf3 o Nc3.")]
    r = play_turn(g, motor, question="¿qué hago?", llm_factory=factory(llm))
    assert r.answer == "Puedes jugar Nf3 o Nc3." and len(llm.llamadas) == 1


def test_hechos_que_contradicen_los_datos():
    from app.coach.graph import hechos_contradichos

    datos = (
        "Bxc6 ...; Balance: cambio igualado, no se gana material; "
        "quedan peones doblados del rival en la columna c"
    )
    # Lo que dijo el coach a Javier
    assert len(hechos_contradichos("Tras dxc6 te quedan peones doblados en la columna c.", datos)) == 1
    assert len(hechos_contradichos("Con Bxc6 ganas el caballo, pero pierdes el par de alfiles.", datos)) == 1
    # Bien dicho: sin avisos
    assert (
        hechos_contradichos("Es un cambio; el rival queda con peones doblados en la columna c.", datos) == []
    )
    assert hechos_contradichos("Tras Qxd8 ganas la dama.", "Balance: GANAS material: +9") == []
    datos_tuyos = "Balance: cambio igualado; quedan peones doblados tuyos en la columna f"
    assert len(hechos_contradichos("El rival queda con peones doblados.", datos_tuyos)) == 1


def test_mas_formas_de_atribuir_los_doblados():
    from app.coach.graph import hechos_contradichos

    datos = "Balance: cambio igualado; quedan peones doblados del rival en la columna c"
    assert len(hechos_contradichos("El rival recaptura con dxc6, dejándote peones doblados.", datos)) == 1
    assert len(hechos_contradichos("Eso podría dejarte peones doblados.", datos)) == 1
    assert hechos_contradichos("Tu rival queda con peones doblados en la columna c.", datos) == []


def test_una_pregunta_obliga_a_usar_herramientas_en_la_primera_llamada(motor):
    class Espia(FakeLLM):
        opciones: list = []

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.opciones.append(kwargs.get("tool_choice"))
            return super()._generate(messages, stop, run_manager, **kwargs)

    llm = Espia(respuestas=[pide("evaluar_posicion"), AIMessage("Igualada.")], llamadas=[], opciones=[])
    play_turn(CoachGame(level=0), motor, question="¿qué plan tengo?", llm_factory=factory(llm))
    assert llm.opciones == ["required", None]  # solo la primera llamada


def test_el_coach_marca_tu_jugada_brillante(engine):
    g = CoachGame(board=chess.Board("r6k/6pp/7N/3Q4/8/8/8/6K1 w - - 0 1"))
    r = g.play_user_move("Qg8+", engine, depth=12)
    assert r.brilliant and r.label == "buena"


# ---------------------------------------------------------------- fuerza por ELO


def test_sin_fuerza_juega_a_elo_1200():
    g = CoachGame()
    assert g.elo == ELO_POR_DEFECTO and g.level is None
    assert CoachGame(level=3).elo is None  # las partidas viejas siguen con su Skill Level


def test_temperatura_baja_al_subir_el_elo():
    assert temperatura(400) == 300 and temperatura(1300) == 60
    assert temperatura(200) == 300 and temperatura(3000) < 60  # fuera de rango, se recorta
    assert temperatura(400) > temperatura(800) > temperatura(1200)


def _veces_la_mejor(elo: int, n: int = 2000) -> float:
    a, b, c = (chess.Move.from_uci(u) for u in ("e2e4", "d2d4", "g1f3"))
    candidatas = [(a, 50), (b, -50), (c, -350)]  # la mejor, pierde un peón, pierde una pieza
    rng = random.Random(7)
    elegidas = [elegir_jugada_debil(candidatas, elo, rng) for _ in range(n)]
    return elegidas.count(a) / n, elegidas.count(c) / n


def test_a_menos_elo_mas_jugadas_peores():
    mejor_400, pieza_400 = _veces_la_mejor(400)
    mejor_1300, pieza_1300 = _veces_la_mejor(1300)
    assert mejor_1300 > 0.8 and pieza_1300 < 0.01  # a 1300 casi siempre la mejor
    assert mejor_400 < 0.6 and pieza_400 > 0.1  # a 400 cuelga piezas a menudo
    assert mejor_400 > pieza_400  # pero la mejor sigue siendo la más probable


@pytest.mark.parametrize("elo", [400, 1320, 2500])
def test_el_coach_juega_con_cualquier_elo(engine, elo):
    g = CoachGame(user_color=chess.BLACK, elo=elo, rng=random.Random(1))
    r = g.play_coach_move(engine, think_time=0.05, depth=6)
    assert r.by == "coach" and g.user_to_move
