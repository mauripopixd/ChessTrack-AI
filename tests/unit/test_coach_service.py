"""CoachService sin BD: repositorio en memoria, LLM falso y Stockfish real (se salta sin él)."""

import contextlib
from datetime import UTC, datetime, timedelta

import chess
import chess.engine
import pytest
from langchain_core.messages import AIMessage

from app.analysis import find_stockfish
from app.coach.game import CoachGame, GameOverError, IllegalMoveError
from app.errors import CoachLLMUnavailableError, CoachRateLimitError
from app.models import CoachGameRecord, CoachMessage, User
from app.services.coach import LIMITE_ALCANZADO, LLM_CAIDO, CoachService, _volcar, cargar
from tests.fakes import FakeLLM, InMemoryCoachRepository

YO = User(id=1, username="ana")
OTRO = User(id=2, username="otro")


@pytest.fixture(scope="module")
def stockfish():
    ruta = find_stockfish()
    if ruta is None:
        pytest.skip("Stockfish no está instalado (ver README)")
    with chess.engine.SimpleEngine.popen_uci(ruta) as eng:
        eng.configure({"Threads": 1})
        yield eng


@pytest.fixture
def motor(stockfish):
    return lambda: contextlib.nullcontext(stockfish)


@pytest.fixture
def llm():
    return FakeLLM(respuestas=[], llamadas=[])


@pytest.fixture
def repo():
    return InMemoryCoachRepository()


class Reloj:
    def __init__(self):
        self.ahora = datetime.now(UTC)

    def __call__(self):
        return self.ahora


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def service(repo, motor, llm, reloj):
    return CoachService(repo, motor, lambda tools: llm, answers_per_hour=3, clock=reloj)


def partida_tras(stockfish, user_id: int, *sans: str, nivel: int = 0) -> CoachGameRecord:
    """Partida (sin guardar) con esas jugadas ya hechas, alternando usuario (blancas) y coach.
    Sirve para empezar desde una posición concreta; el coach real no juega lo que queremos."""
    game = CoachGame(level=nivel)
    for i, san in enumerate(sans):
        quien = "user" if i % 2 == 0 else "coach"
        game._jugar(game.board.parse_san(san), quien, stockfish, chess.engine.Limit(depth=6))
    record = CoachGameRecord(user_id=user_id, user_color="white", level=nivel, messages=[])
    _volcar(record, game)
    return record


# ---------------------------------------------------------------- crear y leer


def test_crear_con_blancas_sin_jugadas(service, repo):
    p = service.create(YO, "white", 3)
    assert p.color == "white" and p.level == 3 and p.move_count == 0 and p.your_turn
    assert p.fen == chess.STARTING_FEN and p.result == "*"
    assert repo.get(YO.id, p.id) is not None


def test_crear_con_negras_el_coach_abre(service):
    p = service.create(YO, "black", 0)
    assert p.move_count == 1 and p.moves[0].by == "coach" and p.your_turn


def test_partida_de_otro_no_existe(service):
    p = service.create(YO, "white", 0)
    assert service.get(OTRO, p.id) is None
    assert service.move(OTRO, p.id, "e4") is None
    assert service.ask(OTRO, p.id, "¿qué tal?") is None
    assert service.delete(OTRO, p.id) is False and service.get(YO, p.id) is not None


def test_cargar_rehace_tablero_informes_y_chat(stockfish):
    record = partida_tras(stockfish, 1, "e4", "d5")
    record.messages = [
        CoachMessage(role="user", content="hola"),
        CoachMessage(role="coach", content="¡hola!"),
    ]
    game = cargar(record)
    assert [m.uci() for m in game.board.move_stack] == ["e2e4", "d7d5"]
    assert game.last_coach_report.san == "d5" and game.chat == [("user", "hola"), ("coach", "¡hola!")]


# ---------------------------------------------------------------- jugadas


def test_jugada_buena_se_guarda_sin_llm(service, repo, llm):
    p = service.create(YO, "white", 0)
    t = service.move(YO, p.id, "e4")
    assert t.your_move.san == "e4" and t.coach_move is not None and t.answer is None and t.note is None
    assert llm.llamadas == []
    guardada = service.get(YO, p.id)
    assert guardada.move_count == 2 and guardada.messages == [] and guardada.fen == t.fen


def test_jugada_ilegal_no_toca_la_partida(service):
    p = service.create(YO, "white", 0)
    with pytest.raises(IllegalMoveError):
        service.move(YO, p.id, "Ke2")
    assert service.get(YO, p.id).move_count == 0


def test_error_se_comenta_y_el_chat_se_guarda(service, repo, stockfish, llm):
    p = repo.create(partida_tras(stockfish, YO.id, "e4", "d5"))
    llm.respuestas = [AIMessage("La dama queda a tiro del alfil de c8.")]
    t = service.move(YO, p.id, "Qg4")
    assert t.your_move.label == "error_grave" and t.answer.startswith("La dama")
    roles = [(m.role, m.content[:20]) for m in repo.get(YO.id, p.id).messages]
    assert roles == [("user", "¿Qué falló en mi jug"), ("coach", "La dama queda a tiro")]


def test_partida_terminada_da_game_over(service, repo, stockfish):
    p = repo.create(partida_tras(stockfish, YO.id, "f3", "e5", "g4", "Qh4#"))
    assert service.get(YO, p.id).result == "0-1" and service.get(YO, p.id).termination == "checkmate"
    with pytest.raises(GameOverError):
        service.move(YO, p.id, "a3")


# ---------------------------------------------------------------- preguntas y límite


def test_pregunta_guarda_pregunta_y_respuesta(service, repo, llm):
    p = service.create(YO, "white", 0)
    llm.respuestas = [AIMessage("Igualada.")]
    t = service.ask(YO, p.id, "¿Voy ganando?")
    assert t.answer == "Igualada." and t.your_move is None
    assert [(m.role, m.content) for m in repo.get(YO.id, p.id).messages] == [
        ("user", "¿Voy ganando?"),
        ("coach", "Igualada."),
    ]
    assert service.remaining_answers(YO) == 2


def test_limite_por_hora_entre_todas_las_partidas(service, repo, stockfish, llm, reloj):
    a, b = service.create(YO, "white", 0), service.create(YO, "white", 0)
    for _ in range(2):
        service.ask(YO, a.id, "¿qué tal?")
    service.ask(YO, b.id, "¿y aquí?")  # 3 de 3, en otra partida
    with pytest.raises(CoachRateLimitError):
        service.ask(YO, b.id, "¿otra?")
    assert service.remaining_answers(OTRO) == 3  # el límite es de cada usuario

    # Las jugadas siguen funcionando, pero un error ya no se comenta
    p = repo.create(partida_tras(stockfish, YO.id, "e4", "d5"))
    llamadas = len(llm.llamadas)
    t = service.move(YO, p.id, "Qg4")
    assert t.your_move.label == "error_grave" and t.answer is None and t.note == LIMITE_ALCANZADO
    assert len(llm.llamadas) == llamadas

    reloj.ahora += timedelta(hours=1, minutes=1)  # pasada la hora, vuelve a haber cupo
    assert service.remaining_answers(YO) == 3
    assert service.ask(YO, a.id, "¿ya?").answer


def test_llm_caido_en_pregunta_da_error_y_no_guarda(service, repo, llm):
    p = service.create(YO, "white", 0)
    llm.falla = True
    with pytest.raises(CoachLLMUnavailableError):
        service.ask(YO, p.id, "¿Voy ganando?")
    assert repo.get(YO.id, p.id).messages == []


def test_llm_caido_en_jugada_la_guarda_igual(service, repo, stockfish, llm):
    p = repo.create(partida_tras(stockfish, YO.id, "e4", "d5"))
    llm.falla = True
    t = service.move(YO, p.id, "Qg4")
    assert t.your_move.san == "Qg4" and t.answer is None and t.note == LLM_CAIDO
    assert service.get(YO, p.id).move_count == 4  # e4 d5 Qg4 y la respuesta del coach


def test_lectura_trae_jugadas_legales_y_fen_de_cada_jugada(service):
    p = service.create(YO, "white", 0)
    assert len(p.legal_moves) == 20 and "e2e4" in p.legal_moves and "g1f3" in p.legal_moves
    service.move(YO, p.id, "e4")
    p = service.get(YO, p.id)
    tablero = chess.Board()
    for m in p.moves:
        tablero.push_uci(m.uci)
        assert m.fen_after == tablero.fen()
    assert p.moves[-1].fen_after == p.fen
    assert set(p.legal_moves) == {m.uci() for m in tablero.legal_moves}


def test_sin_jugadas_legales_si_no_es_tu_turno(service, repo, stockfish):
    p = repo.create(partida_tras(stockfish, YO.id, "f3", "e5", "g4", "Qh4#"))
    assert service.get(YO, p.id).legal_moves == []


# ---------------------------------------------------------------- tablas


def test_reglas_para_aceptar_tablas():
    from app.coach.game import coach_acepta_tablas

    assert coach_acepta_tablas(-300, 10)[0]  # va peor: le convienen, aunque sea pronto
    assert not coach_acepta_tablas(250, 60)[0]  # va mejor: sigue
    acepta, motivo = coach_acepta_tablas(0, 10)
    assert not acepta and "pronto" in motivo
    assert coach_acepta_tablas(10, 40)[0]  # igualada desde la jugada 15
    assert not coach_acepta_tablas(60, 40)[0]  # ligera ventaja: lo intenta


def test_reglas_para_ofrecer_tablas():
    from app.coach.game import coach_ofrece_tablas

    muerta = [5, -10, 0, 12, -3, 8]
    assert coach_ofrece_tablas(muerta, 44, None)
    assert not coach_ofrece_tablas(muerta, 30, None)  # antes de la jugada 20
    assert not coach_ofrece_tablas(muerta, 44, 34)  # ofreció hace poco
    assert coach_ofrece_tablas(muerta, 60, 34)
    assert not coach_ofrece_tablas([5, -10, 0, 12, -3, 80], 44, None)  # alguien va mejor


def test_tablas_pronto_y_con_igualdad_se_rechazan(service):
    p = service.create(YO, "white", 0)
    r = service.offer_draw(YO, p.id)
    assert not r.accepted and "pronto" in r.message and r.result == "*"
    assert service.get(YO, p.id).your_turn


def test_tablas_aceptadas_si_el_coach_va_peor_y_la_partida_termina(service, repo, stockfish):
    # 1.e4 e5 2.Nf3 Nf6 3.Nxe5 Nxe4 4.Qe2 Nf6?? 5.Nc6+ Be7: las blancas ganan la dama
    p = repo.create(
        partida_tras(
            stockfish, YO.id, *["e4", "e5", "Nf3", "Nf6", "Nxe5", "Nxe4", "Qe2", "Nf6", "Nc6+", "Be7"]
        )
    )
    r = service.offer_draw(YO, p.id)
    assert r.accepted and r.result == "1/2-1/2" and r.termination == "agreement"
    leida = service.get(YO, p.id)
    assert leida.result == "1/2-1/2" and not leida.your_turn and leida.legal_moves == []
    with pytest.raises(GameOverError):
        service.move(YO, p.id, "Nxd8")
    with pytest.raises(GameOverError):
        service.offer_draw(YO, p.id)


def test_oferta_del_coach_se_acepta_o_se_rechaza(service, repo, stockfish):
    p = repo.create(partida_tras(stockfish, YO.id, "e4", "e5"))
    p.draw_offer = "coach"  # como si la hubiera ofrecido tras su jugada
    assert service.get(YO, p.id).draw_offer == "coach"
    assert service.decline_draw(YO, p.id) and service.get(YO, p.id).draw_offer is None
    p.draw_offer = "coach"
    r = service.offer_draw(YO, p.id)  # aceptarla: sin consultar al motor, aunque sea pronto
    assert r.accepted and r.termination == "agreement"


def test_jugar_rechaza_la_oferta_pendiente(service, repo, stockfish):
    p = repo.create(partida_tras(stockfish, YO.id, "e4", "e5"))
    p.draw_offer = "coach"
    service.move(YO, p.id, "Nf3")
    assert service.get(YO, p.id).draw_offer is None


# ---------------------------------------------------------------- rendirse


@pytest.mark.parametrize(("color", "gana"), [("white", "0-1"), ("black", "1-0")])
def test_rendirse_da_la_partida_al_coach(service, color, gana):
    p = service.create(YO, color, 0)
    leida = service.resign(YO, p.id)
    assert leida.result == gana and leida.termination == "resignation"
    assert not leida.your_turn and leida.legal_moves == []
    assert service.get(YO, p.id).result == gana  # queda guardado
    with pytest.raises(GameOverError):
        service.move(YO, p.id, "e4" if color == "white" else "e5")
    with pytest.raises(GameOverError):
        service.resign(YO, p.id)
    assert service.resign(OTRO, p.id) is None
