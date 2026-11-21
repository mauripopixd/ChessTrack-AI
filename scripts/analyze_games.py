"""Analiza con Stockfish tus partidas de data/raw/ y guarda una fila por jugada en un CSV.

Es la entrada del notebook de la Etapa 3 y de los datos de entrenamiento de la Etapa 4.
Usa varios hilos, cada uno con su propio Stockfish de 1 hilo de CPU: cada partida es
independiente, así que N motores en paralelo van casi N veces más rápido. Hilos (no
procesos) porque Stockfish ya es un programa aparte y Python solo espera su respuesta;
además, ProcessPoolExecutor + chess.engine se bloquea en Windows.

    python -m scripts.analyze_games                       # 500 más recientes, profundidad 12
    python -m scripts.analyze_games --games 2000 --depth 14 --workers 12

Necesita Stockfish (ver README) y los PGN de scripts/download_games.py.
"""

import argparse
import csv
import io
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from app.analysis import analyze_moves, find_stockfish

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
SALIDA = RAIZ / "data" / "analysis" / "moves.csv"

COLUMNAS_PARTIDA = [
    "game_id", "utc_datetime", "white", "black", "white_elo", "black_elo",
    "user_color", "result", "termination", "time_control",
]  # fmt: skip
COLUMNAS_JUGADA = [
    "ply", "mover", "is_user", "san", "uci", "best_uci", "eval_before", "eval_after",
    "cp_loss", "win_before", "win_after", "win_drop", "label", "clock_after",
]  # fmt: skip


class Motores:
    """Un Stockfish por hilo, abierto la primera vez que el hilo lo necesita y reutilizado
    después (abrirlo por partida costaría más que analizarla)."""

    def __init__(self, ruta: str) -> None:
        self.ruta = ruta
        self._local = threading.local()
        self._todos: list[chess.engine.SimpleEngine] = []
        self._lock = threading.Lock()

    def del_hilo(self) -> chess.engine.SimpleEngine:
        if not hasattr(self._local, "engine"):
            engine = chess.engine.SimpleEngine.popen_uci(self.ruta)
            engine.configure({"Threads": 1, "Hash": 64})
            self._local.engine = engine
            with self._lock:
                self._todos.append(engine)
        return self._local.engine

    def cerrar(self) -> None:
        for engine in self._todos:
            engine.quit()


def _analizar(pgn: str, player: str, motores: Motores, limit: chess.engine.Limit) -> list[dict]:
    game = chess.pgn.read_game(io.StringIO(pgn))
    h = game.headers
    nodos = list(game.mainline())
    if not nodos:
        return []
    color = {h.get("White", "").lower(): "white", h.get("Black", "").lower(): "black"}.get(player.lower())
    partida = {
        "game_id": h.get("Link") or h.get("Site", ""),
        "utc_datetime": f"{h.get('UTCDate', '')} {h.get('UTCTime', '')}".strip(),
        "white": h.get("White"),
        "black": h.get("Black"),
        "white_elo": h.get("WhiteElo"),
        "black_elo": h.get("BlackElo"),
        "user_color": color,
        "result": h.get("Result"),
        "termination": h.get("Termination"),
        "time_control": h.get("TimeControl"),
    }
    evals = analyze_moves(
        [n.move.uci() for n in nodos], motores.del_hilo(), limit, initial_fen=game.board().fen()
    )
    filas = []
    for nodo, ev in zip(nodos, evals, strict=True):
        fila = partida | ev.to_dict()
        fila["is_user"] = ev.mover == color
        fila["clock_after"] = nodo.clock()  # segundos que le quedan a quien movió ({[%clk ...]})
        filas.append(fila)
    return filas


def _partidas_recientes(n: int) -> list[str]:
    """Las n partidas más recientes de data/raw/, ordenadas por fecha UTC."""
    partidas = []
    for ruta in sorted(RAW.glob("*.pgn")):
        with open(ruta, encoding="utf-8") as f:
            while (game := chess.pgn.read_game(f)) is not None:
                h = game.headers
                partidas.append((f"{h.get('UTCDate', '')} {h.get('UTCTime', '')}", str(game)))
    partidas.sort()
    return [pgn for _, pgn in partidas[-n:]]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--games", type=int, default=500, help="partidas más recientes (por defecto 500)")
    parser.add_argument("--depth", type=int, default=12, help="profundidad de Stockfish (por defecto 12)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--player", default="weytey", help="tu usuario en los PGN")
    parser.add_argument("--out", type=Path, default=SALIDA)
    args = parser.parse_args()

    ruta = find_stockfish()
    if ruta is None:
        print("No encuentro Stockfish: instálalo o define STOCKFISH_PATH (ver README)", file=sys.stderr)
        return 1
    partidas = _partidas_recientes(args.games)
    if not partidas:
        print("No hay partidas en data/raw/ (ejecuta scripts/download_games.py download)", file=sys.stderr)
        return 1

    print(f"{len(partidas)} partidas, profundidad {args.depth}, {args.workers} motores", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    inicio = time.perf_counter()
    filas_total = 0
    motores, limit = Motores(ruta), chess.engine.Limit(depth=args.depth)
    try:
        with (
            open(args.out, "w", newline="", encoding="utf-8") as f,
            ThreadPoolExecutor(args.workers) as pool,
        ):
            writer = csv.DictWriter(f, fieldnames=COLUMNAS_PARTIDA + COLUMNAS_JUGADA)
            writer.writeheader()
            futuros = [pool.submit(_analizar, pgn, args.player, motores, limit) for pgn in partidas]
            for i, futuro in enumerate(as_completed(futuros), start=1):
                filas = futuro.result()
                writer.writerows(filas)
                filas_total += len(filas)
                if i % 50 == 0 or i == len(partidas):
                    seg = time.perf_counter() - inicio
                    print(f"  {i}/{len(partidas)} partidas, {filas_total} jugadas, {seg:.0f} s", flush=True)
    finally:
        motores.cerrar()  # aunque algo falle, no dejar procesos de Stockfish colgados
    print(f"Listo: {args.out} ({filas_total} jugadas, {time.perf_counter() - inicio:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
