"""Checkpoint de la Etapa 5B: una partida COMPLETA contra el coach, con explicaciones a petición.

El "usuario" es Stockfish con Skill Level bajo (comete errores de verdad, que el coach
comenta) y hace preguntas en jugadas fijas. Guarda la transcripción en Markdown.

    python -m scripts.coach_demo                         # → docs/coach_partida_ejemplo.md
    python -m scripts.coach_demo --nivel-usuario 2 --nivel-coach 6 --teoria

Con LANGSMITH_TRACING=true y LANGSMITH_API_KEY en .env, cada turno queda trazado en LangSmith
y todos comparten el mismo thread_id (la partida entera se ve como un hilo).
"""

import argparse
import contextlib
import sys
import time
import uuid
from pathlib import Path

import chess
import chess.engine

from app.analysis import find_stockfish
from app.coach.game import CoachGame
from app.coach.session import TurnResult, enable_tracing_from_env_file, play_turn
from app.coach.tools import ETIQUETA
from app.config import get_settings
from scripts.coach_cli import cargar_retriever, pgn

PREGUNTAS = {  # número de jugada del usuario → pregunta
    3: "¿Cómo se llama esta apertura y cuál es la idea?",
    10: "¿Voy ganando o perdiendo, y qué plan me recomiendas?",
    20: "¿Qué amenaza el coach con su última jugada?",
    30: "¿Cuál ha sido mi peor jugada hasta ahora y por qué?",
}


def jugada_del_usuario(eng: chess.engine.SimpleEngine, board: chess.Board, nivel: int) -> str:
    r = eng.play(board, chess.engine.Limit(time=0.05), options={"Skill Level": nivel})
    return board.san(r.move)


def bloque(r: TurnResult, segundos: float) -> str:
    texto = ""
    if r.answer:
        texto += f"\n> **Coach** ({r.model or 'LLM'}, {segundos:.1f} s): " + r.answer.replace("\n", "\n> ")
        for f in r.sources:
            texto += f"\n>\n> {f}"
        texto += "\n"
    return texto


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nivel-usuario", type=int, default=2)
    p.add_argument("--nivel-coach", type=int, default=4)
    p.add_argument("--max-jugadas", type=int, default=60, help="jugadas del usuario como mucho")
    p.add_argument("--pausa", type=float, default=6.0, help="segundos tras cada llamada al LLM (límite Groq)")
    p.add_argument("--teoria", action="store_true")
    p.add_argument("--salida", type=Path, default=Path("docs/coach_partida_ejemplo.md"))
    args = p.parse_args()

    trazas = enable_tracing_from_env_file()
    retriever = cargar_retriever() if args.teoria else None
    from app.ml.classifier import ErrorClassifier

    clasificador = ErrorClassifier.load(get_settings().classifier_path)
    hilo = str(uuid.uuid4())
    game = CoachGame(level=args.nivel_coach)
    lineas = [
        "# Partida de ejemplo contra el coach (checkpoint de la Etapa 5B)\n",
        f"Generada con `python -m scripts.coach_demo`. Usuario simulado: Stockfish Skill Level "
        f"{args.nivel_usuario}; coach: nivel {args.nivel_coach}. Teoría de aperturas: "
        f"{'sí' if retriever else 'no'}. Trazas en LangSmith: {'sí' if trazas else 'no'}.\n",
        "Los comentarios tras un error los dispara el grafo solo; las preguntas son del usuario.\n",
    ]
    llamadas, tiempos, modelos = 0, [], {}
    with chess.engine.SimpleEngine.popen_uci(get_settings().stockfish_path or find_stockfish()) as eng:
        motor = lambda: contextlib.nullcontext(eng)  # noqa: E731
        comunes = {"classifier": clasificador, "retriever": retriever,
                   "trace_metadata": {"thread_id": hilo, "demo": True}}  # fmt: skip
        n = 0
        while game.result() is None and n < args.max_jugadas:
            n += 1
            san = jugada_del_usuario(eng, game.board, args.nivel_usuario)
            t = time.perf_counter()
            r = play_turn(game, motor, move=san, **comunes)
            seg = time.perf_counter() - t
            u, c = r.user_move, r.coach_move
            linea = f"**{n}.** Tú: {u.san} — {ETIQUETA[u.label]}"
            if u.label != "buena" and u.best_san:
                linea += f" (mejor {u.best_san})"
            linea += f" · Coach: {c.san}" if c else ""
            lineas.append(linea + "  " + bloque(r, seg))
            print(linea, "· comentario" if r.answer else "")
            if r.answer:
                llamadas, tiempos = llamadas + 1, [*tiempos, seg]
                modelos[r.model] = modelos.get(r.model, 0) + 1
                time.sleep(args.pausa)
            if n in PREGUNTAS and game.result() is None:
                t = time.perf_counter()
                r = play_turn(game, motor, question=PREGUNTAS[n], **comunes)
                seg = time.perf_counter() - t
                lineas.append(f"\n**Pregunta:** {PREGUNTAS[n]}\n" + bloque(r, seg))
                print("  pregunta:", PREGUNTAS[n])
                llamadas, tiempos = llamadas + 1, [*tiempos, seg]
                modelos[r.model] = modelos.get(r.model, 0) + 1
                time.sleep(args.pausa)

    etiquetas = [x.label for x in game.reports if x.by == "user"]
    resumen = ", ".join(f"{ETIQUETA[e]} {etiquetas.count(e)}" for e in ETIQUETA if etiquetas.count(e))
    tiempos.sort()
    errores = sum(1 for e in etiquetas if e in ("error", "error_grave"))
    lineas += [
        "\n## Resumen\n",
        f"- Resultado: {game.result() or 'sin terminar (tope de jugadas)'}",
        f"- Jugadas del usuario: {len(etiquetas)} ({resumen})",
        f"- Turnos con LLM: {llamadas} · mediana {tiempos[len(tiempos) // 2] if tiempos else 0:.1f} s · "
        + ", ".join(f"{m}: {k}" for m, k in modelos.items()),
        f"- Turnos sin LLM (jugada buena o imprecisión): {len(etiquetas) - errores}",
        "\n## PGN\n",
        "```\n" + pgn(game) + "\n```\n",
    ]
    args.salida.write_text("\n".join(lineas), encoding="utf-8")
    print(f"\n{game.result()} · {llamadas} turnos con LLM → {args.salida}")


if __name__ == "__main__":
    main()
