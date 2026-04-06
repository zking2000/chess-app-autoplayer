"""
Read Chess.app board state via macOS Accessibility API.

Chess.app exposes each of the 64 board squares as a button inside
group 1 of the main window. Button descriptions follow these patterns:

  "白兵, e2"    occupied: <piece_name>, <square>
  "e4"          empty: just <square>

This module parses those descriptions to reconstruct the piece map and
to detect which move was made between two successive states.
"""
from __future__ import annotations

import subprocess
import chess

from .position_recognizer import move_changed_squares  # reuse existing helper


# ── Piece name maps (Chinese + English for portability) ──────────────────────

_PIECE_MAP: dict[str, chess.Piece] = {
    "白车": chess.Piece(chess.ROOK, chess.WHITE),
    "白马": chess.Piece(chess.KNIGHT, chess.WHITE),
    "白象": chess.Piece(chess.BISHOP, chess.WHITE),
    "白后": chess.Piece(chess.QUEEN, chess.WHITE),
    "白王": chess.Piece(chess.KING, chess.WHITE),
    "白兵": chess.Piece(chess.PAWN, chess.WHITE),
    "黑车": chess.Piece(chess.ROOK, chess.BLACK),
    "黑马": chess.Piece(chess.KNIGHT, chess.BLACK),
    "黑象": chess.Piece(chess.BISHOP, chess.BLACK),
    "黑后": chess.Piece(chess.QUEEN, chess.BLACK),
    "黑王": chess.Piece(chess.KING, chess.BLACK),
    "黑兵": chess.Piece(chess.PAWN, chess.BLACK),
    "White Rook": chess.Piece(chess.ROOK, chess.WHITE),
    "White Knight": chess.Piece(chess.KNIGHT, chess.WHITE),
    "White Bishop": chess.Piece(chess.BISHOP, chess.WHITE),
    "White Queen": chess.Piece(chess.QUEEN, chess.WHITE),
    "White King": chess.Piece(chess.KING, chess.WHITE),
    "White Pawn": chess.Piece(chess.PAWN, chess.WHITE),
    "Black Rook": chess.Piece(chess.ROOK, chess.BLACK),
    "Black Knight": chess.Piece(chess.KNIGHT, chess.BLACK),
    "Black Bishop": chess.Piece(chess.BISHOP, chess.BLACK),
    "Black Queen": chess.Piece(chess.QUEEN, chess.BLACK),
    "Black King": chess.Piece(chess.KING, chess.BLACK),
    "Black Pawn": chess.Piece(chess.PAWN, chess.BLACK),
}

_READ_SCRIPT = """\
tell application "System Events"
    tell process "{app}"
        set grp to group 1 of window 1
        set outStr to ""
        repeat with btn in (every button of grp)
            set outStr to outStr & (description of btn) & linefeed
        end repeat
        return outStr
    end tell
end tell
"""


def read_piece_map(app_name: str = "Chess") -> dict[chess.Square, chess.Piece]:
    """Return a mapping of occupied square → piece from the live Chess.app state."""
    script = _READ_SCRIPT.format(app=app_name)
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    piece_map: dict[chess.Square, chess.Piece] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if ", " not in line:
            continue
        sep = line.rfind(", ")
        piece_name = line[:sep]
        sq_name = line[sep + 2:]
        piece = _PIECE_MAP.get(piece_name)
        if piece is None or len(sq_name) != 2:
            continue
        try:
            piece_map[chess.parse_square(sq_name)] = piece
        except ValueError:
            pass
    return piece_map


def infer_move_from_piece_maps(
    before: dict[chess.Square, chess.Piece],
    after: dict[chess.Square, chess.Piece],
    board: chess.Board,
) -> chess.Move | None:
    """Infer the chess move between two successive piece maps.

    Handles normal moves, captures, en passant, castling, and promotions
    by comparing changed squares against each legal move's expected footprint.
    """
    changed: set[chess.Square] = {
        sq
        for sq in set(before) | set(after)
        if before.get(sq) != after.get(sq)
    }
    if not changed:
        return None

    for move in board.legal_moves:
        if move_changed_squares(board, move) == changed:
            return move
    return None
