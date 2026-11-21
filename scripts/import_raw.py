"""Importa archivos PGN grandes directamente en la BD, sin pasar por la API.

`POST /games` limita los archivos a 5 MB; este script es para cargar tu historial
completo de `data/raw/` (descargado con download_games.py). Usa la misma lógica
que la API (app/services/games.py), así que respeta duplicados y colores.

El usuario debe existir (regístralo antes con POST /auth/register):

    python -m scripts.import_raw --user weytey                  # todo data/raw/*.pgn
    python -m scripts.import_raw --user javier --player weytey data/raw/weytey_2026_10.pgn
"""

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import select

from app.db import get_session_factory
from app.models import User
from app.pgn_parser import InvalidPGNError
from app.services.games import import_pgn

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--user", required=True, help="username de la app")
    parser.add_argument("--player", help="tu nombre dentro del PGN (por defecto, el username)")
    parser.add_argument("archivos", nargs="*", type=Path, help="por defecto, data/raw/*.pgn")
    args = parser.parse_args()

    archivos = args.archivos or sorted(RAW.glob("*.pgn"))
    if not archivos:
        print("No hay archivos .pgn (¿ejecutaste scripts/download_games.py download?)", file=sys.stderr)
        return 1

    with get_session_factory()() as session:
        user = session.scalars(select(User).where(User.username == args.user.lower())).first()
        if user is None:
            print(
                f"No existe el usuario {args.user!r}: regístralo antes con POST /auth/register",
                file=sys.stderr,
            )
            return 1

        totales = {"creadas": 0, "repetidas": 0, "inválidas": 0}
        inicio = time.perf_counter()
        for ruta in archivos:
            try:
                r = import_pgn(session, user, ruta.read_text(encoding="utf-8"), player=args.player)
            except InvalidPGNError as e:
                print(f"{ruta.name}: {e}")
                continue
            totales["creadas"] += len(r.created)
            totales["repetidas"] += len(r.duplicates)
            totales["inválidas"] += len(r.errors)
            print(
                f"{ruta.name:<24} creadas {len(r.created):>4}  repetidas {len(r.duplicates):>4}  "
                f"inválidas {len(r.errors):>3}"
            )
        print(f"\nTotal: {totales}  ({time.perf_counter() - inicio:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
