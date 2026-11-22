"""Una partida contra el coach: estado, jugadas del usuario y respuestas del motor.

Todo lo que no necesita inteligencia se hace aquí con código normal, no con el LLM:
validar la jugada, que Stockfish responda y etiquetar la jugada del usuario. Es fiable,
determinista y no gasta el límite del LLM gratuito. El LLM (graph.py) solo entra para
EXPLICAR, y lee el estado de esta clase en vez de recibir FEN o jugadas copiadas por él.
"""

from dataclasses import dataclass, field

import chess
import chess.engine

from app.analysis import CP_LOSS_MAX, MATE_CP, classify, win_probability


class IllegalMoveError(ValueError):
    """La jugada no es legal o no se entiende (ni SAN ni UCI)."""


class GameOverError(ValueError):
    """La partida ya terminó."""


@dataclass(frozen=True)
class MoveReport:
    """Qué pasó en una jugada, desde el punto de vista de quien la hizo."""

    ply: int
    san: str
    uci: str
    by: str  # "user" o "coach"
    eval_before: int  # cp desde blancas
    eval_after: int
    cp_loss: int
    win_drop: float
    label: str
    best_san: str | None  # mejor jugada según el motor en la posición previa
    best_line: list[str] = field(default_factory=list)  # continuación tras la mejor (SAN)


@dataclass
class CoachGame:
    user_color: bool = chess.WHITE
    level: int = 5  # "Skill Level" de Stockfish (0-20): fuerza del coach como rival
    board: chess.Board = field(default_factory=chess.Board)
    reports: list[MoveReport] = field(default_factory=list)
    chat: list[tuple[str, str]] = field(default_factory=list)  # (rol, texto) de las preguntas

    @property
    def user_to_move(self) -> bool:
        return self.board.turn == self.user_color and not self.board.is_game_over()

    @property
    def last_user_report(self) -> MoveReport | None:
        return next((r for r in reversed(self.reports) if r.by == "user"), None)

    @property
    def last_coach_report(self) -> MoveReport | None:
        return next((r for r in reversed(self.reports) if r.by == "coach"), None)

    def parse_move(self, texto: str) -> chess.Move:
        """Acepta SAN ("Nf3", "O-O", "exd5") o UCI ("g1f3")."""
        texto = texto.strip()
        try:
            return self.board.parse_san(texto)
        except chess.IllegalMoveError:  # notación válida, pero no se puede jugar aquí
            raise IllegalMoveError(f"{texto} no es legal en esta posición") from None
        except chess.AmbiguousMoveError:  # "Nd2" con dos caballos que pueden ir
            raise IllegalMoveError(f"{texto} es ambigua: indica la pieza (p. ej. Nbd2)") from None
        except ValueError:  # no es SAN: se prueba como UCI
            pass
        try:
            move = chess.Move.from_uci(texto.lower())
        except ValueError:
            raise IllegalMoveError(
                f"No entiendo la jugada {texto!r} (usa SAN como Nf3 o UCI como g1f3)"
            ) from None
        if move not in self.board.legal_moves:
            raise IllegalMoveError(f"{texto} no es legal en esta posición")
        return move

    def _evaluar(self, engine: chess.engine.SimpleEngine, limit: chess.engine.Limit):
        """(cp desde blancas, mejor jugada, línea principal) de la posición actual."""
        if self.board.is_checkmate():
            return (-MATE_CP if self.board.turn == chess.WHITE else MATE_CP), None, []
        if self.board.is_game_over(claim_draw=False):
            return 0, None, []
        info = engine.analyse(self.board, limit)
        pv = info.get("pv") or []
        return info["score"].white().score(mate_score=MATE_CP), (pv[0] if pv else None), pv

    def _jugar(self, move: chess.Move, by: str, engine: chess.engine.SimpleEngine, limit) -> MoveReport:
        mover = self.board.turn
        antes, mejor, pv = self._evaluar(engine, limit)
        mejor_san = self.board.san(mejor) if mejor else None
        linea = _san_linea(self.board, pv[:6])
        san = self.board.san(move)
        self.board.push(move)
        despues, _, _ = self._evaluar(engine, limit)
        signo = 1 if mover == chess.WHITE else -1
        caida = max(0.0, win_probability(signo * antes) - win_probability(signo * despues))
        informe = MoveReport(
            ply=len(self.board.move_stack),
            san=san,
            uci=move.uci(),
            by=by,
            eval_before=antes,
            eval_after=despues,
            cp_loss=min(CP_LOSS_MAX, max(0, signo * (antes - despues))),
            win_drop=round(caida, 2),
            label=classify(caida),
            best_san=mejor_san,
            best_line=linea,
        )
        self.reports.append(informe)
        return informe

    def play_user_move(self, texto: str, engine: chess.engine.SimpleEngine, depth: int = 12) -> MoveReport:
        if self.board.is_game_over():
            raise GameOverError("La partida ya terminó")
        if self.board.turn != self.user_color:
            raise IllegalMoveError("No es tu turno")
        return self._jugar(self.parse_move(texto), "user", engine, chess.engine.Limit(depth=depth))

    def play_coach_move(
        self, engine: chess.engine.SimpleEngine, think_time: float = 0.3, depth: int = 12
    ) -> MoveReport | None:
        """El motor juega con la fuerza `level` (Skill Level solo durante esta orden)."""
        if self.board.is_game_over() or self.board.turn == self.user_color:
            return None
        resultado = engine.play(
            self.board, chess.engine.Limit(time=think_time), options={"Skill Level": self.level}
        )
        return self._jugar(resultado.move, "coach", engine, chess.engine.Limit(depth=depth))

    def result(self) -> str | None:
        """None si sigue; si no, "1-0", "0-1" o "1/2-1/2" y el motivo."""
        if not self.board.is_game_over():
            return None
        r = self.board.outcome()
        motivo = r.termination.name.lower().replace("_", " ")
        return f"{r.result()} ({motivo})"


def _san_linea(board: chess.Board, moves: list[chess.Move]) -> list[str]:
    copia = board.copy(stack=False)
    sans = []
    for m in moves:
        if m not in copia.legal_moves:
            break
        sans.append(copia.san(m))
        copia.push(m)
    return sans
