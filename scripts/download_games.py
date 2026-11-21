"""Descarga partidas de chess.com y elige muestras para los tests.

Usa la API pública de chess.com (https://www.chess.com/news/view/published-data-api),
que no requiere login. Tres subcomandos:

    python scripts/download_games.py download --months 3   # últimos 3 meses a data/raw/
    python scripts/download_games.py list                  # tabla de partidas en data/raw/
    python scripts/download_games.py pick 4 17 30 41 52    # copia esas partidas a data/samples/
"""

import argparse
import time
import urllib.error
import urllib.request
import json
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn

USUARIO = "weytey"
RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
SAMPLES = RAIZ / "data" / "samples"
API = "https://api.chess.com/pub/player/{usuario}/games/archives"
# chess.com pide un User-Agent identificable; sin él puede responder 403.
HEADERS = {"User-Agent": "pgn-downloader/0.1 (python urllib)"}
PAUSA_SEG = 1.0  # chess.com recomienda peticiones en serie, sin ráfagas


# ---------------------------------------------------------------- descarga


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def listar_archivos(usuario: str) -> list[str]:
    """URLs de los archivos mensuales del usuario, del más antiguo al más reciente."""
    datos = json.loads(_get(API.format(usuario=usuario.lower())))
    return datos["archives"]


def descargar(usuario: str, meses: int | None, forzar: bool) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    archivos = listar_archivos(usuario)
    if meses is not None:
        archivos = archivos[-meses:]

    for i, url in enumerate(archivos):
        anio, mes = url.rstrip("/").split("/")[-2:]
        destino = RAW / f"{usuario.lower()}_{anio}_{mes}.pgn"
        # El mes más reciente puede tener partidas nuevas: siempre se vuelve a bajar.
        es_ultimo = i == len(archivos) - 1
        if destino.exists() and not forzar and not es_ultimo:
            print(f"ya existe   {destino.name}")
            continue
        try:
            pgn = _get(url + "/pgn")
        except urllib.error.HTTPError as e:
            print(f"error {e.code}  {url}")
            continue
        destino.write_bytes(pgn)
        n = pgn.count(b"[Event ")
        print(f"descargado  {destino.name}  ({n} partidas)")
        time.sleep(PAUSA_SEG)


# ---------------------------------------------------------------- listado


@dataclass
class Resumen:
    indice: int
    archivo: str
    fecha: str
    color: str
    resultado: str
    jugadas: int
    ritmo: str
    variante: str
    final: str
    extras: str


def _extras(game: chess.pgn.Game) -> str:
    """Marca jugadas especiales útiles para cubrir casos en los tests."""
    marcas = set()
    board = game.board()
    for move in game.mainline_moves():
        if board.is_queenside_castling(move):
            marcas.add("O-O-O")
        if board.is_en_passant(move):
            marcas.add("e.p.")
        if move.promotion:
            pieza = chess.piece_symbol(move.promotion).upper()
            marcas.add("=D" if pieza == "Q" else f"={pieza}")
        board.push(move)
    return " ".join(sorted(marcas))


def leer_partidas() -> list[tuple[Path, chess.pgn.Game]]:
    """Todas las partidas de data/raw/, en orden estable (por archivo y posición)."""
    partidas = []
    for ruta in sorted(RAW.glob("*.pgn")):
        with open(ruta, encoding="utf-8") as f:
            while (game := chess.pgn.read_game(f)) is not None:
                partidas.append((ruta, game))
    return partidas


def resumir(indice: int, ruta: Path, game: chess.pgn.Game, usuario: str) -> Resumen:
    h = game.headers
    color = "blancas" if h.get("White", "").lower() == usuario.lower() else "negras"
    plies = sum(1 for _ in game.mainline_moves())
    final = h.get("Termination", "?").replace(usuario, "yo")
    return Resumen(
        indice=indice,
        archivo=ruta.stem,
        fecha=h.get("Date", "?"),
        color=color,
        resultado=h.get("Result", "?"),
        jugadas=(plies + 1) // 2,
        ritmo=h.get("TimeControl", "?"),
        variante=h.get("Variant", "estándar"),
        final=final,
        extras=_extras(game),
    )


def listar(usuario: str) -> None:
    partidas = leer_partidas()
    if not partidas:
        print("No hay partidas en data/raw/. Ejecuta primero: download")
        return
    print(f"{len(partidas)} partidas en data/raw/\n")
    print(f"{'#':>4}  {'fecha':<10}  {'color':<7}  {'result':<7}  {'jug':>3}  "
          f"{'ritmo':<7}  {'variante':<9}  {'extras':<14}  final")
    for i, (ruta, game) in enumerate(partidas):
        r = resumir(i, ruta, game, usuario)
        print(f"{r.indice:>4}  {r.fecha:<10}  {r.color:<7}  {r.resultado:<7}  "
              f"{r.jugadas:>3}  {r.ritmo:<7}  {r.variante[:9]:<9}  {r.extras:<14}  "
              f"{r.final[:40]}")


# ---------------------------------------------------------------- muestras


def elegir(indices: list[int]) -> None:
    partidas = leer_partidas()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    elegidas = []
    for n, i in enumerate(indices, start=1):
        if not 0 <= i < len(partidas):
            raise SystemExit(f"Índice fuera de rango: {i} (hay {len(partidas)} partidas)")
        _, game = partidas[i]
        texto = str(game)
        (SAMPLES / f"partida{n}.pgn").write_text(texto + "\n", encoding="utf-8")
        elegidas.append(texto)
    (SAMPLES / "varias.pgn").write_text("\n\n".join(elegidas) + "\n", encoding="utf-8")
    print(f"Listo: {len(indices)} partidas + varias.pgn en data/samples/")


# ---------------------------------------------------------------- CLI


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", default=USUARIO, help=f"usuario de chess.com (por defecto {USUARIO})")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_down = sub.add_parser("download", help="descarga archivos mensuales a data/raw/")
    p_down.add_argument("--months", type=int, help="solo los últimos N meses (por defecto, todos)")
    p_down.add_argument("--force", action="store_true", help="vuelve a bajar meses ya descargados")

    sub.add_parser("list", help="muestra las partidas de data/raw/")

    p_pick = sub.add_parser("pick", help="copia partidas elegidas a data/samples/")
    p_pick.add_argument("indices", type=int, nargs="+", help="números de la columna # de 'list'")

    args = parser.parse_args()
    if args.comando == "download":
        descargar(args.user, args.months, args.force)
    elif args.comando == "list":
        listar(args.user)
    else:
        elegir(args.indices)


if __name__ == "__main__":
    main()
