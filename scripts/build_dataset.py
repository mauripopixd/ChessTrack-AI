"""Une las etiquetas de Stockfish (analyze_games) con las variables del tablero (app/ml/features).

Entrada:  data/analysis/moves*.csv  (una fila por jugada, con su etiqueta)
Salida:   data/analysis/dataset.csv (las mismas filas + las columnas de FEATURES)

    python -m scripts.build_dataset                                  # moves.csv
    python -m scripts.build_dataset --moves data/analysis/moves_all.csv

Usa varios procesos: calcular amenazas y mates en 1 es Python puro (CPU), y cada
partida es independiente.
"""

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from app.ml.features import FEATURES, game_features

RAIZ = Path(__file__).resolve().parent.parent
ANALISIS = RAIZ / "data" / "analysis"
# Columnas del análisis que se conservan junto a las variables.
CONSERVAR = [
    "game_id",
    "utc_datetime",
    "ply",
    "mover",
    "is_user",
    "san",
    "uci",
    "cp_loss",
    "win_drop",
    "label",
]


def _variables_partida(args: tuple[list[str], list[float | None]]) -> list[dict]:
    jugadas, relojes = args
    return game_features(jugadas, relojes)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--moves", type=Path, default=ANALISIS / "moves.csv")
    parser.add_argument("--out", type=Path, default=ANALISIS / "dataset.csv")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()

    inicio = time.perf_counter()
    moves = pd.read_csv(args.moves, dtype={"time_control": str}).sort_values(["game_id", "ply"])
    partidas = [g for _, g in moves.groupby("game_id", sort=False)]
    tareas = [(g.uci.tolist(), [None if pd.isna(c) else float(c) for c in g.clock_after]) for g in partidas]
    print(f"{len(partidas)} partidas, {len(moves)} jugadas, {args.workers} procesos", flush=True)

    with ProcessPoolExecutor(args.workers) as pool:
        variables = list(pool.map(_variables_partida, tareas, chunksize=20))

    bloques = [
        pd.concat([g[CONSERVAR].reset_index(drop=True), pd.DataFrame(v, columns=FEATURES)], axis=1)
        for g, v in zip(partidas, variables, strict=True)
    ]
    dataset = pd.concat(bloques, ignore_index=True)
    dataset.to_csv(args.out, index=False)
    print(f"Listo: {args.out} ({len(dataset)} filas, {time.perf_counter() - inicio:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
