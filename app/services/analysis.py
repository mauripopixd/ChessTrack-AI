"""Análisis de una partida guardada: Stockfish jugada a jugada + clasificador (Etapa 4).

Sin SQL ni HTTP. Recibe por inyección:
- un GameRepository (dónde se guarda),
- un Analyzer (quién evalúa: Stockfish en la API, uno falso en los tests),
- un ErrorClassifier opcional (si no hay modelo entrenado, el análisis va sin él).
"""

import io
from typing import Protocol

import chess
import chess.engine
import chess.pgn

from app.analysis import ETIQUETAS, MoveEval, analyze_moves
from app.engine import EnginePool
from app.ml.classifier import ErrorClassifier
from app.ml.features import game_features
from app.models import Game, MoveAnalysis, User
from app.repositories.games import GameRepository
from app.schemas import (
    AnalysisSummary,
    FlaggedMove,
    GameAnalysisRead,
    ModelComparison,
    MoveAnalysisRead,
)

ERRORES = {"error", "error_grave"}


class NotAnalyzedError(Exception):
    """La partida existe pero todavía no se ha analizado."""


class Analyzer(Protocol):
    depth: int

    def analyze(self, moves_uci: list[str], initial_fen: str) -> list[MoveEval]: ...


class StockfishAnalyzer:
    def __init__(self, pool: EnginePool, depth: int) -> None:
        self.pool = pool
        self.depth = depth

    def analyze(self, moves_uci: list[str], initial_fen: str) -> list[MoveEval]:
        with self.pool.engine() as engine:
            return analyze_moves(moves_uci, engine, chess.engine.Limit(depth=self.depth), initial_fen)


def _desde_pgn(pgn: str) -> tuple[str, list[float | None]]:
    """Posición inicial y relojes ([%clk]) del PGN guardado: la tabla moves no los tiene."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    return game.board().fen(), [nodo.clock() for nodo in game.mainline()]


class AnalysisService:
    def __init__(
        self, games: GameRepository, analyzer: Analyzer, classifier: ErrorClassifier | None = None
    ) -> None:
        self.games = games
        self.analyzer = analyzer
        self.classifier = classifier

    def analyze(self, user: User, game_id: int, force: bool = False) -> GameAnalysisRead | None:
        """Analiza y guarda. Si ya estaba analizada, devuelve lo guardado (salvo force=True).
        None si la partida no existe o es de otro usuario. Lanza EngineUnavailableError."""
        game = self.games.get_with_analysis(user.id, game_id)
        if game is None:
            return None
        if game.analyzed_at is not None and not force:
            return self._leer(game)

        jugadas = [m.uci for m in game.moves]
        fen_inicial, relojes = _desde_pgn(game.pgn_raw)
        evals = self.analyzer.analyze(jugadas, fen_inicial)
        probs: list[float | None] = [None] * len(jugadas)
        if self.classifier is not None and jugadas:
            variables = game_features(jugadas, relojes[: len(jugadas)], initial_fen=fen_inicial)
            probs = self.classifier.error_probs(variables)

        analisis = [
            MoveAnalysis(
                eval_before=ev.eval_before,
                eval_after=ev.eval_after,
                cp_loss=ev.cp_loss,
                win_drop=ev.win_drop,
                label=ev.label,
                best_uci=ev.best_uci,
                error_prob=prob,
            )
            for ev, prob in zip(evals, probs, strict=True)
        ]
        self.games.save_analysis(game, analisis, self.analyzer.depth)
        return self._leer(game)

    def get(self, user: User, game_id: int) -> GameAnalysisRead | None:
        """None si no existe o es ajena; NotAnalyzedError si es tuya pero no está analizada."""
        game = self.games.get_with_analysis(user.id, game_id)
        if game is None:
            return None
        if game.analyzed_at is None:
            raise NotAnalyzedError
        return self._leer(game)

    # ------------------------------------------------------------ lectura

    def _leer(self, game: Game) -> GameAnalysisRead:
        board = chess.Board(_desde_pgn(game.pgn_raw)[0])
        umbral = self.classifier.umbral if self.classifier is not None else None
        filas = []
        for move in game.moves:
            a = move.analysis
            mover = "white" if board.turn == chess.WHITE else "black"
            mejor = board.san(chess.Move.from_uci(a.best_uci)) if a.best_uci else None
            numero = board.fullmove_number
            board.push_uci(move.uci)
            filas.append(
                MoveAnalysisRead(
                    ply=move.ply,
                    move_number=numero,
                    san=move.san,
                    mover=mover,
                    is_user=None if game.user_color is None else mover == game.user_color,
                    eval_before=a.eval_before,
                    eval_after=a.eval_after,
                    cp_loss=a.cp_loss,
                    win_drop=a.win_drop,
                    label=a.label,
                    best_move=mejor,
                    error_prob=a.error_prob,
                    model_flag=None if a.error_prob is None or umbral is None else a.error_prob >= umbral,
                )
            )

        # Resumen sobre MIS jugadas; si no se sabe mi color, sobre todas.
        mias = [f for f in filas if f.is_user is not False]
        resumen = AnalysisSummary(
            user_color=game.user_color,
            moves_analyzed=len(mias),
            acpl=round(sum(f.cp_loss for f in mias) / len(mias), 1) if mias else None,
            labels={e: sum(f.label == e for f in mias) for e in ETIQUETAS},
            errors=[
                FlaggedMove(
                    ply=f.ply,
                    move_number=f.move_number,
                    san=f.san,
                    label=f.label,
                    cp_loss=f.cp_loss,
                    best_move=f.best_move,
                )  # fmt: skip
                for f in mias
                if f.label in ERRORES
            ],
        )
        return GameAnalysisRead(
            game_id=game.id,
            depth=game.analysis_depth,
            analyzed_at=game.analyzed_at,
            summary=resumen,
            model=_comparar(mias, umbral),
            moves=filas,
        )


def _comparar(filas: list[MoveAnalysisRead], umbral: float | None) -> ModelComparison | None:
    if umbral is None or not filas or any(f.model_flag is None for f in filas):
        return None
    sf = sum(f.label in ERRORES for f in filas)
    modelo = sum(bool(f.model_flag) for f in filas)
    ambos = sum(f.label in ERRORES and bool(f.model_flag) for f in filas)
    return ModelComparison(
        threshold=umbral,
        stockfish_errors=sf,
        model_flags=modelo,
        both=ambos,
        precision=round(ambos / modelo, 3) if modelo else None,
        recall=round(ambos / sf, 3) if sf else None,
    )
