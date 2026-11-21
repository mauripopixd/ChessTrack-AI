"""Imprime cada jugada (SAN y FEN) y el resultado de un archivo PGN.

Uso, desde la raíz del repo:

    python -m scripts.print_pgn data/samples/partida1.pgn
"""

import sys
from pathlib import Path

from app.pgn_parser import InvalidPGNError, parse_pgn_many


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    ruta = Path(sys.argv[1])
    try:
        games = parse_pgn_many(ruta.read_text(encoding="utf-8"))
    except InvalidPGNError as e:
        print(f"PGN inválido: {e}", file=sys.stderr)
        return 1

    for n, game in enumerate(games, start=1):
        fecha = game.played_at.strftime("%Y-%m-%d %H:%M UTC") if game.played_at else "?"
        print(f"=== Partida {n}: {game.white or '?'} vs {game.black or '?'}  ({fecha})")
        for move in game.moves:
            numero = f"{(move.ply + 1) // 2}." if move.ply % 2 else f"{move.ply // 2}..."
            print(f"{numero:>5} {move.san:<8} {move.fen_after}")
        print(f"Resultado: {game.result}  |  {game.headers.get('Termination', '')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
