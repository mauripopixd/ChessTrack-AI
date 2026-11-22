"""Juega contra el coach en la terminal y pregúntale lo que quieras.

    python -m scripts.coach_cli                  # blancas, nivel 5
    python -m scripts.coach_cli --color negras --nivel 10 --teoria

Escribe una jugada (e4, Nf3, O-O o g1f3) o una pregunta ("¿por qué fue un error?").
Comandos: /tablero, /pgn, /salir.

Si LANGSMITH_TRACING=true y LANGSMITH_API_KEY están en .env, cada turno queda trazado en
LangSmith (proyecto LANGSMITH_PROJECT).
"""

import argparse
import contextlib
import sys
import time
import uuid
from datetime import date

import chess
import chess.engine
import chess.pgn

from app.analysis import find_stockfish
from app.coach.game import CoachGame, IllegalMoveError
from app.coach.session import TurnResult, enable_tracing_from_env_file, play_turn
from app.coach.tools import ETIQUETA
from app.config import get_settings

COMANDOS = {"/tablero", "/pgn", "/salir"}


def es_pregunta(texto: str) -> bool:
    return "?" in texto or "¿" in texto or len(texto.split()) > 2


def pgn(game: CoachGame) -> str:
    partida = chess.pgn.Game.from_board(game.board)
    partida.headers["White"] = "Tú" if game.user_color == chess.WHITE else f"Coach (nivel {game.level})"
    partida.headers["Black"] = "Tú" if game.user_color == chess.BLACK else f"Coach (nivel {game.level})"
    partida.headers["Event"] = "ChessTrack AI · partida contra el coach"
    partida.headers["Date"] = date.today().strftime("%Y.%m.%d")
    return str(partida)


def imprimir_turno(r: TurnResult, segundos: float) -> None:
    if r.error:
        print(f"  ✗ {r.error}")
        return
    if r.user_move:
        u = r.user_move
        mejor = f" · Stockfish prefería {u.best_san}" if u.label != "buena" and u.best_san else ""
        print(f"  Tú: {u.san} → {ETIQUETA[u.label]}{mejor}")
    if r.coach_move:
        print(f"  Coach: {r.coach_move.san}")
    if r.answer:
        print(f"\n  Coach dice ({r.model or 'LLM'}, {segundos:.1f} s):\n  " + r.answer.replace("\n", "\n  "))
    for fuente in r.sources:
        print("  " + fuente)
    if r.result:
        print(f"\n  Partida terminada: {r.result}")


def cargar_retriever():
    from app.deps import RAGUnavailableError, get_opening_assistant

    try:
        return get_opening_assistant().retriever
    except (RAGUnavailableError, ValueError) as e:
        print(f"(Sin teoría de aperturas: {e})")
        return None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--color", choices=["blancas", "negras"], default="blancas")
    p.add_argument("--nivel", type=int, default=5, help="fuerza del coach, 0-20 (Skill Level de Stockfish)")
    p.add_argument("--teoria", action="store_true", help="cargar el RAG de aperturas (bge-m3, unos segundos)")
    args = p.parse_args()

    trazas = enable_tracing_from_env_file()
    print("Trazas en LangSmith: " + ("sí" if trazas else "no (faltan LANGSMITH_* en .env)"))
    retriever = cargar_retriever() if args.teoria else None
    from app.ml.classifier import ErrorClassifier

    clasificador = ErrorClassifier.load(get_settings().classifier_path)
    partida_id = str(uuid.uuid4())  # thread_id: LangSmith agrupa los turnos como un hilo

    game = CoachGame(user_color=chess.WHITE if args.color == "blancas" else chess.BLACK, level=args.nivel)
    with chess.engine.SimpleEngine.popen_uci(get_settings().stockfish_path or find_stockfish()) as eng:
        motor = lambda: contextlib.nullcontext(eng)  # noqa: E731 - un solo motor en el CLI
        if game.user_color == chess.BLACK:
            print(f"  Coach: {game.play_coach_move(eng).san}")
        print(game.board.unicode(invert_color=True, empty_square="·", orientation=game.user_color))
        while game.result() is None:
            try:
                texto = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not texto:
                continue
            if texto in COMANDOS:
                if texto == "/salir":
                    break
                print(pgn(game) if texto == "/pgn" else game.board.unicode(
                    invert_color=True, empty_square="·", orientation=game.user_color))  # fmt: skip
                continue
            try:
                game.parse_move(texto)
                turno = {"move": texto}
            except IllegalMoveError as e:
                if not es_pregunta(texto):
                    print(f"  ✗ {e}")
                    continue
                turno = {"question": texto}
            t = time.perf_counter()
            r = play_turn(
                game, motor, **turno, classifier=clasificador, retriever=retriever,
                trace_metadata={"thread_id": partida_id, "level": game.level},
            )  # fmt: skip
            imprimir_turno(r, time.perf_counter() - t)
            if r.coach_move:
                print(game.board.unicode(invert_color=True, empty_square="·", orientation=game.user_color))
    print("\n" + pgn(game))


if __name__ == "__main__":
    main()
