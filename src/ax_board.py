"""
Read Chess.app board state via macOS Accessibility API.

Chess.app exposes each of the 64 board squares as a button inside
group 1 of the main window. Button descriptions follow these patterns:

  "白兵, e2"    occupied: <piece_name>, <square>
  "e4"          empty: just <square>

This module parses those descriptions to reconstruct the piece map and
to detect which move was made between two successive states.

Resume support
--------------
``board_from_live_state()`` reads the current Chess.app position and
reconstructs a ``chess.Board`` suitable for resuming a mid-game session.
Castling rights are inferred from king/rook positions; en passant and
precise move counters cannot be recovered from a snapshot and are left
at their defaults (safe conservative values).
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
tell application "{app}" to activate
delay 0.3
tell application "System Events"
    tell process "{app}"
        set frontmost to true
        set retries to 0
        repeat
            set wins to windows
            if (count of wins) > 0 then exit repeat
            delay 0.3
            set retries to retries + 1
            if retries > 10 then return ""
        end repeat
        set grp to first group of (item 1 of wins)
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


_TITLE_SCRIPT = """\
tell application "{app}" to activate
delay 0.3
tell application "System Events"
    tell process "{app}"
        set frontmost to true
        set retries to 0
        repeat
            set wins to windows
            if (count of wins) > 0 then exit repeat
            delay 0.3
            set retries to retries + 1
            if retries > 10 then return "unknown"
        end repeat
        return title of (item 1 of wins)
    end tell
end tell
"""


def read_turn(app_name: str = "Chess") -> chess.Color | None:
    """Return whose turn it is by reading the Chess.app window title.

    The title contains "(白方走棋)" / "(White to Move)" for white's turn
    and "(黑方走棋)" / "(Black to Move)" for black's turn.
    Returns None if the turn cannot be determined (e.g. game over screen).
    """
    script = _TITLE_SCRIPT.format(app=app_name)
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    title = result.stdout.strip().lower()
    if "白方" in title or "white" in title:
        return chess.WHITE
    if "黑方" in title or "black" in title:
        return chess.BLACK
    return None


def _infer_turn_from_check(board: chess.Board) -> chess.Color | None:
    """Infer side to move from check status (more reliable than window title).

    If exactly one king is in check, that side must move next.  If neither is
    in check, returns None (caller should use the window title).  If both are
    in check, the position is illegal.
    """
    wk = board.king(chess.WHITE)
    bk = board.king(chess.BLACK)
    if wk is None or bk is None:
        return None

    white_checked = board.is_attacked_by(chess.BLACK, wk)
    black_checked = board.is_attacked_by(chess.WHITE, bk)

    if white_checked and black_checked:
        raise RuntimeError(
            "Both kings are in check — position is illegal. "
            "Wait for Chess.app animations to finish and try again."
        )
    if white_checked:
        return chess.WHITE
    if black_checked:
        return chess.BLACK
    return None


def _infer_castling(
    piece_map: dict[chess.Square, chess.Piece],
) -> str:
    """Return a castling-rights string (e.g. 'KQkq') inferred from piece positions.

    A side retains its castling right only if both its king and the relevant
    rook are still on their original squares.  This is conservative: it may
    grant rights that were already forfeited by an earlier king/rook move, but
    it never denies rights that are genuinely available.
    """
    rights = ""
    white_king_ok = piece_map.get(chess.E1) == chess.Piece(chess.KING, chess.WHITE)
    black_king_ok = piece_map.get(chess.E8) == chess.Piece(chess.KING, chess.BLACK)

    if white_king_ok and piece_map.get(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE):
        rights += "K"
    if white_king_ok and piece_map.get(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE):
        rights += "Q"
    if black_king_ok and piece_map.get(chess.H8) == chess.Piece(chess.ROOK, chess.BLACK):
        rights += "k"
    if black_king_ok and piece_map.get(chess.A8) == chess.Piece(chess.ROOK, chess.BLACK):
        rights += "q"
    return rights or "-"


def board_from_live_state(app_name: str = "Chess") -> chess.Board:
    """Reconstruct a chess.Board from the current Chess.app position.

    Reads piece positions and whose turn it is directly from the live UI.
    Castling rights are inferred from king/rook placement; en passant is
    assumed absent (cannot be determined from a snapshot).

    Raises RuntimeError if the board cannot be read or appears invalid
    (e.g. missing a king).
    """
    piece_map = read_piece_map(app_name)
    if not piece_map:
        raise RuntimeError(
            "Failed to read board from Chess.app — no pieces found. "
            "Make sure Chess.app is open and a game is in progress."
        )

    # Validate: both kings must be present
    white_kings = [sq for sq, p in piece_map.items()
                   if p == chess.Piece(chess.KING, chess.WHITE)]
    black_kings = [sq for sq, p in piece_map.items()
                   if p == chess.Piece(chess.KING, chess.BLACK)]
    if len(white_kings) != 1 or len(black_kings) != 1:
        raise RuntimeError(
            f"Invalid board: found {len(white_kings)} white king(s) and "
            f"{len(black_kings)} black king(s)."
        )

    castling = _infer_castling(piece_map)

    # Build FEN: <pieces> <turn> <castling> <en_passant> <halfmove> <fullmove>
    board = chess.Board(None)  # start with empty board
    for square, piece in piece_map.items():
        board.set_piece_at(square, piece)
    board.set_castling_fen(castling)
    board.ep_square = None      # cannot recover en passant from snapshot
    board.halfmove_clock = 0    # conservative (resets draw-by-50 counter)
    board.fullmove_number = 1   # approximate; affects nothing functionally

    # Turn order: prefer check-based inference (Chess.app title can lag after promotions).
    turn_from_check = _infer_turn_from_check(board)
    if turn_from_check is not None:
        board.turn = turn_from_check
    else:
        title_turn = read_turn(app_name)
        if title_turn is not None:
            board.turn = title_turn
        else:
            board.turn = chess.WHITE
            print("Warning: could not infer turn (no check, unreadable title); assuming White.")

    if not board.is_valid():
        # Title may disagree with reality — try the other side once.
        board.turn = not board.turn
        if not board.is_valid():
            board.turn = not board.turn  # restore for error message
            raise RuntimeError(
                f"Reconstructed board is not valid (FEN: {board.fen()}). "
                "Wait for Chess.app piece animations to finish, then run again with --resume."
            )

    return board


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
