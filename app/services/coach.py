"""Partidas contra el coach por la API (Etapa 5B, PR 2).

Sin SQL ni HTTP. Cada turno:
1. lee la partida de la BD bloqueando su fila (dos turnos a la vez no se pisan),
2. la reconstruye como `CoachGame` (tablero + informes + chat),
3. ejecuta el grafo (app/coach/session.play_turn),
4. guarda las jugadas nuevas y los mensajes del chat.

Límite por usuario: N respuestas del LLM por hora entre todas sus partidas, porque el cupo
gratuito de Groq es de la organización y un solo usuario podría agotarlo para todos. Al
llegar al límite, /ask responde 429 y las jugadas siguen, pero sin comentario automático.
"""

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import chess
import chess.engine
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from app.coach.game import (
    CoachGame,
    GameOverError,
    MoveReport,
    coach_acepta_tablas,
    coach_ofrece_tablas,
)
from app.coach.session import TurnResult, play_turn
from app.coach.tools import MotorFn
from app.errors import CoachLLMUnavailableError, CoachRateLimitError
from app.models import CoachGameRecord, CoachMessage, User
from app.repositories.coach import CoachRepository
from app.schemas import (
    CoachDrawRead,
    CoachGamePage,
    CoachGameRead,
    CoachGameSummary,
    CoachMessageRead,
    CoachMoveRead,
    CoachTurnRead,
)

LIMITE_ALCANZADO = "Sin comentario: has llegado al límite de respuestas del coach de esta hora."
LLM_CAIDO = "Sin comentario: el LLM no está disponible ahora (la jugada se guardó)."


def _color(c: bool) -> str:
    return "white" if c == chess.WHITE else "black"


def cargar(record: CoachGameRecord) -> CoachGame:
    """La partida guardada, lista para jugar: se rehace el tablero con las jugadas en orden."""
    game = CoachGame(
        user_color=chess.WHITE if record.user_color == "white" else chess.BLACK, level=record.level
    )
    for d in record.moves:
        game.board.push_uci(d["uci"])
        game.reports.append(MoveReport(**d))
    game.chat = [(m.role, m.content) for m in record.messages]
    game.acuerdo = record.termination == "agreement"
    game.abandono = record.termination == "resignation"
    return game


def _volcar(record: CoachGameRecord, game: CoachGame) -> None:
    # Lista nueva (no .append): SQLAlchemy solo detecta cambios en un JSONB si se reasigna.
    record.moves = [asdict(r) for r in game.reports]
    if game.acuerdo:
        record.result, record.termination = "1/2-1/2", "agreement"
        return
    if game.abandono:
        record.result, record.termination = game.resultado_abandono, "resignation"
        return
    salida = game.board.outcome()
    record.result = salida.result() if salida else "*"
    record.termination = salida.termination.name.lower() if salida else None


def _jugada(r: MoveReport | None, fen_after: str | None = None) -> CoachMoveRead | None:
    if r is None:
        return None
    return CoachMoveRead(
        ply=r.ply, san=r.san, uci=r.uci, by=r.by, label=r.label, eval_before=r.eval_before,
        eval_after=r.eval_after, cp_loss=r.cp_loss, win_drop=r.win_drop, best_move=r.best_san,
        fen_after=fen_after, brilliant=r.brilliant,
    )  # fmt: skip


def _jugadas_con_fen(game: CoachGame) -> list[CoachMoveRead]:
    """Cada jugada con la posición que deja: la web anima la última a partir de la anterior."""
    tablero = game.board.root()
    salida = []
    for r in game.reports:
        tablero.push_uci(r.uci)
        salida.append(_jugada(r, tablero.fen()))
    return salida


def _resumen(record: CoachGameRecord) -> CoachGameSummary:
    return CoachGameSummary(
        id=record.id, color=record.user_color, level=record.level, result=record.result,
        termination=record.termination, move_count=len(record.moves), created_at=record.created_at,
        updated_at=record.updated_at,
    )  # fmt: skip


class CoachService:
    def __init__(
        self,
        repo: CoachRepository,
        motor: MotorFn,
        llm_factory: Callable[[list[BaseTool]], BaseChatModel],
        *,
        classifier=None,
        retriever=None,
        answers_per_hour: int = 20,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repo = repo
        self.motor = motor
        self.llm_factory = llm_factory
        self.classifier = classifier
        self.retriever = retriever
        self.answers_per_hour = answers_per_hour
        self.clock = clock

    # ------------------------------------------------------------ lectura

    def read(self, record: CoachGameRecord, game: CoachGame | None = None) -> CoachGameRead:
        game = game or cargar(record)
        return CoachGameRead(
            **_resumen(record).model_dump(),
            fen=game.board.fen(),
            your_turn=game.user_to_move,
            draw_offer=record.draw_offer,
            legal_moves=[m.uci() for m in game.board.legal_moves] if game.user_to_move else [],
            moves=_jugadas_con_fen(game),
            messages=[CoachMessageRead.model_validate(m) for m in record.messages],
        )

    def get(self, user: User, game_id: int) -> CoachGameRead | None:
        record = self.repo.get(user.id, game_id)
        return self.read(record) if record else None

    def list(self, user: User, limit: int, offset: int) -> CoachGamePage:
        filas, total = self.repo.list_page(user.id, limit, offset)
        return CoachGamePage(items=[_resumen(r) for r in filas], total=total, limit=limit, offset=offset)

    def remaining_answers(self, user: User) -> int:
        usadas = self.repo.coach_answers_since(user.id, self.clock() - timedelta(hours=1))
        return max(0, self.answers_per_hour - usadas)

    # ------------------------------------------------------------ escritura

    def create(self, user: User, color: str, level: int) -> CoachGameRead:
        game = CoachGame(user_color=chess.WHITE if color == "white" else chess.BLACK, level=level)
        if game.user_color == chess.BLACK:  # con negras, el coach abre
            with self.motor() as eng:
                game.play_coach_move(eng)
        record = CoachGameRecord(user_id=user.id, user_color=color, level=level, messages=[])
        _volcar(record, game)
        return self.read(self.repo.create(record), game)

    def move(self, user: User, game_id: int, move: str) -> CoachTurnRead | None:
        """None si la partida no existe o es de otro. Lanza IllegalMoveError (jugada ilegal o
        ilegible), GameOverError o EngineUnavailableError, sin tocar la partida."""
        record = self.repo.get(user.id, game_id, for_update=True)
        if record is None:
            return None
        game = cargar(record)
        if game.terminada:
            raise GameOverError("La partida ya terminó")
        game.parse_move(move)  # valida antes del grafo para lanzar el error con su tipo
        record.draw_offer = None  # jugar rechaza la oferta de tablas que hubiera
        comentar = self.remaining_answers(user) > 0
        r = self._turno(record, game, move=move, comment_errors=comentar)
        nota = None
        if r.user_move and r.user_move.label in ("error", "error_grave") and not r.answer:
            nota = LLM_CAIDO if comentar else LIMITE_ALCANZADO
        ply = len(game.reports)
        if not game.terminada and coach_ofrece_tablas(
            [x.eval_after for x in game.reports], ply, record.last_draw_offer_ply
        ):
            record.draw_offer, record.last_draw_offer_ply = "coach", ply
        return self._guardar(record, game, r, nota)

    # ------------------------------------------------------------ tablas

    def offer_draw(self, user: User, game_id: int) -> CoachDrawRead | None:
        """El usuario ofrece tablas (o acepta las que ofreció el coach). El coach decide con la
        evaluación de Stockfish (coach_acepta_tablas). Lanza GameOverError o EngineUnavailableError."""
        record = self.repo.get(user.id, game_id, for_update=True)
        if record is None:
            return None
        game = cargar(record)
        if game.terminada:
            raise GameOverError("La partida ya terminó")
        if record.draw_offer == "coach":
            aceptadas, motivo = True, "Tablas aceptadas: el coach te las había ofrecido."
        else:
            with self.motor() as eng:
                info = eng.analyse(game.board, chess.engine.Limit(depth=12))
            cp_blancas = info["score"].white().score(mate_score=10_000)
            cp_coach = cp_blancas if game.user_color == chess.BLACK else -cp_blancas
            aceptadas, motivo = coach_acepta_tablas(cp_coach, len(game.reports))
        if aceptadas:
            game.acordar_tablas()
            record.draw_offer = None
            _volcar(record, game)
        self.repo.save_turn(record, [])
        return CoachDrawRead(
            accepted=aceptadas, message=motivo, result=record.result, termination=record.termination
        )

    def resign(self, user: User, game_id: int) -> CoachGameRead | None:
        """El usuario se rinde: gana el coach. None si no existe; GameOverError si ya terminó."""
        record = self.repo.get(user.id, game_id, for_update=True)
        if record is None:
            return None
        game = cargar(record)
        game.rendirse()
        record.draw_offer = None
        _volcar(record, game)
        self.repo.save_turn(record, [])
        return self.read(record, game)

    def decline_draw(self, user: User, game_id: int) -> bool:
        """Rechaza la oferta del coach (seguir jugando). False si la partida no existe."""
        record = self.repo.get(user.id, game_id, for_update=True)
        if record is None:
            return False
        record.draw_offer = None
        self.repo.save_turn(record, [])
        return True

    def ask(self, user: User, game_id: int, question: str) -> CoachTurnRead | None:
        """None si no existe. Lanza CoachRateLimitError o CoachLLMUnavailableError."""
        record = self.repo.get(user.id, game_id, for_update=True)
        if record is None:
            return None
        if self.remaining_answers(user) <= 0:
            raise CoachRateLimitError(self.answers_per_hour)
        game = cargar(record)
        r = self._turno(record, game, question=question)
        if not r.answer:
            raise CoachLLMUnavailableError(r.llm_error or "El LLM no devolvió respuesta")
        return self._guardar(record, game, r, None)

    def delete(self, user: User, game_id: int) -> bool:
        record = self.repo.get(user.id, game_id)
        if record is None:
            return False
        self.repo.delete(record)
        return True

    # ------------------------------------------------------------ interno

    def _turno(self, record: CoachGameRecord, game: CoachGame, **turno) -> TurnResult:
        return play_turn(
            game, self.motor, llm_factory=self.llm_factory, classifier=self.classifier,
            retriever=self.retriever,
            # LangSmith agrupa los turnos de una partida como un hilo
            trace_metadata={"thread_id": f"coach-game-{record.id}", "user_id": record.user_id},
            **turno,
        )  # fmt: skip

    def _guardar(self, record: CoachGameRecord, game: CoachGame, r: TurnResult, nota: str | None):
        antes = len(record.messages)
        nuevos = [
            CoachMessage(
                user_id=record.user_id, role=rol, content=texto, model=(r.model if rol == "coach" else None)
            )
            for rol, texto in game.chat[antes:]
        ]
        _volcar(record, game)
        self.repo.save_turn(record, nuevos)
        return CoachTurnRead(
            your_move=_jugada(r.user_move),
            coach_move=_jugada(r.coach_move),
            answer=r.answer,
            sources=r.sources,
            model=r.model,
            note=nota,
            fen=game.board.fen(),
            your_turn=game.user_to_move,
            result=record.result,
            termination=record.termination,
            draw_offer=record.draw_offer,
        )
