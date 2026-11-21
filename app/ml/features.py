"""Variables de una jugada calculadas SOLO con el tablero (sin Stockfish).

Las etiquetas salen de la evaluación de Stockfish: si el modelo la recibiera como entrada,
"acertaría" copiándola. Aquí solo hay lo que ve un jugador: material, piezas atacadas,
qué se captura, jaques, amenazas del rival tras la jugada, fase y reloj.

La idea es aproximar, en microsegundos, la pregunta "¿esta jugada huele a error?",
que Stockfish responde en decenas de milisegundos.
"""

from collections.abc import Sequence

import chess

VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

# Orden fijo de columnas: el modelo entrenado depende de él.
FEATURES = [
    # contexto
    "ply", "mover_is_white", "legal_moves", "in_check_before",
    # material (desde quien mueve)
    "material_mover", "material_rival", "material_diff", "material_total",
    # la jugada
    "piece_value", "is_capture", "captured_value", "is_check", "is_promotion", "is_castling",
    # amenazas antes de mover
    "hanging_mine_before", "hanging_mine_before_max", "hanging_theirs_before_max",
    # después de mover
    "hanging_mine_after", "hanging_mine_after_max", "hanging_mine_delta",
    "moved_piece_hanging", "rival_captures", "rival_checks", "rival_mate_in_1",
    "king_zone_attacks", "free_capture_missed",
    # reloj
    "clock_after", "time_spent",
]  # fmt: skip


def _material(board: chess.Board, color: chess.Color) -> int:
    return sum(VALOR[p.piece_type] for p in board.piece_map().values() if p.color == color)


def _colgando(board: chess.Board, color: chess.Color) -> list[int]:
    """Valores de las piezas de `color` que el rival puede ganar: atacadas y sin defensa,
    o atacadas por una pieza de menos valor (el clásico "caballo por dama")."""
    valores = []
    for casilla, pieza in board.piece_map().items():
        if pieza.color != color or pieza.piece_type == chess.KING:
            continue
        atacantes = board.attackers(not color, casilla)
        if not atacantes:
            continue
        menor = min(VALOR[board.piece_type_at(a)] or 10 for a in atacantes)  # el rey "vale" 10 aquí
        if not board.attackers(color, casilla) or menor < VALOR[pieza.piece_type]:
            valores.append(VALOR[pieza.piece_type])
    return valores


def _ataques_zona_rey(board: chess.Board, color: chess.Color) -> int:
    rey = board.king(color)
    if rey is None:
        return 0
    zona = chess.SquareSet(chess.BB_KING_ATTACKS[rey]) | chess.SquareSet.from_square(rey)
    return sum(len(board.attackers(not color, c)) for c in zona)


def _mate_en_1(board: chess.Board) -> bool:
    """¿El que mueve ahora (el rival, tras nuestra jugada) tiene mate inmediato?"""
    for jugada in board.legal_moves:
        if board.gives_check(jugada):
            board.push(jugada)
            mate = board.is_checkmate()
            board.pop()
            if mate:
                return True
    return False


def move_features(
    board: chess.Board,
    move: chess.Move,
    ply: int,
    clock_after: float | None = None,
    time_spent: float | None = None,
) -> dict[str, float]:
    """Variables de `move` jugada en `board` (que no se modifica)."""
    yo = board.turn
    rival = not yo
    pieza = board.piece_at(move.from_square)
    capturada = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        capturada = chess.Piece(chess.PAWN, rival)

    material_mio, material_rival = _material(board, yo), _material(board, rival)
    colgando_antes = _colgando(board, yo)
    regaladas_antes = _colgando(board, rival)

    f = {
        "ply": ply,
        "mover_is_white": int(yo == chess.WHITE),
        "legal_moves": board.legal_moves.count(),
        "in_check_before": int(board.is_check()),
        "material_mover": material_mio,
        "material_rival": material_rival,
        "material_diff": material_mio - material_rival,
        "material_total": material_mio + material_rival,
        "piece_value": VALOR[pieza.piece_type] if pieza else 0,
        "is_capture": int(capturada is not None),
        "captured_value": VALOR[capturada.piece_type] if capturada else 0,
        "is_check": int(board.gives_check(move)),
        "is_promotion": int(move.promotion is not None),
        "is_castling": int(board.is_castling(move)),
        "hanging_mine_before": len(colgando_antes),
        "hanging_mine_before_max": max(colgando_antes, default=0),
        "hanging_theirs_before_max": max(regaladas_antes, default=0),
    }

    board.push(move)
    try:
        colgando_despues = _colgando(board, yo)
        destino_atacado = bool(board.attackers(rival, move.to_square))
        destino_defendido = bool(board.attackers(yo, move.to_square))
        f |= {
            "hanging_mine_after": len(colgando_despues),
            "hanging_mine_after_max": max(colgando_despues, default=0),
            "hanging_mine_delta": sum(colgando_despues) - sum(colgando_antes),
            "moved_piece_hanging": int(destino_atacado and not destino_defendido),
            "rival_captures": sum(1 for m in board.legal_moves if board.is_capture(m)),
            "rival_checks": sum(1 for m in board.legal_moves if board.gives_check(m)),
            "rival_mate_in_1": int(_mate_en_1(board)),
            "king_zone_attacks": _ataques_zona_rey(board, yo),
            # Había una pieza rival gratis y no se capturó nada de ese valor o más.
            "free_capture_missed": int(
                f["hanging_theirs_before_max"] > 0 and f["captured_value"] < f["hanging_theirs_before_max"]
            ),
        }
    finally:
        board.pop()

    f["clock_after"] = clock_after if clock_after is not None else -1.0
    f["time_spent"] = time_spent if time_spent is not None else -1.0
    return f


def game_features(
    moves_uci: Sequence[str],
    clocks: Sequence[float | None] | None = None,
    initial_fen: str = chess.STARTING_FEN,
) -> list[dict[str, float]]:
    """Variables de todas las jugadas de una partida. `clocks[i]` es el tiempo que le
    queda a quien hizo la jugada i (como [%clk] de chess.com); de ahí sale el tiempo gastado."""
    board = chess.Board(initial_fen)
    clocks = list(clocks) if clocks is not None else [None] * len(moves_uci)
    ultimo_reloj: dict[bool, float | None] = {chess.WHITE: None, chess.BLACK: None}
    filas = []
    for ply, (uci, reloj) in enumerate(zip(moves_uci, clocks, strict=True), start=1):
        move = chess.Move.from_uci(uci)
        anterior = ultimo_reloj[board.turn]
        gastado = anterior - reloj if anterior is not None and reloj is not None else None
        filas.append(move_features(board, move, ply, clock_after=reloj, time_spent=gastado))
        ultimo_reloj[board.turn] = reloj
        board.push(move)
    return filas
