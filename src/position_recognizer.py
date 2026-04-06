from __future__ import annotations

import json
from dataclasses import dataclass

import chess
import numpy as np
from PIL import Image

from .board_capture import image_to_gray_array, iter_cells
from .config import TEMPLATE_MANIFEST_PATH, TEMPLATES_DIR


EMPTY_SCORE_THRESHOLD = 9.0
MIN_PIECE_SIGNAL = 12.0


@dataclass
class RecognitionResult:
    board_fen: str
    occupied_count: int


@dataclass
class BoardSnapshot:
    cells: dict[chess.Square, np.ndarray]


def _square_color(row: int, col: int, board_bottom: str) -> str:
    if board_bottom == "white":
        is_light = (row + col) % 2 == 1
    else:
        is_light = (row + col) % 2 == 0
    return "light" if is_light else "dark"


def _screen_cell_to_square(row: int, col: int, board_bottom: str) -> chess.Square:
    if board_bottom == "white":
        file_idx = col
        rank_idx = 7 - row
    else:
        file_idx = 7 - col
        rank_idx = row
    return chess.square(file_idx, rank_idx)


def _load_gray_template(filename: str) -> np.ndarray:
    path = TEMPLATES_DIR / filename
    return image_to_gray_array(Image.open(path))


def _resize_to_match(array: np.ndarray, target: np.ndarray) -> np.ndarray:
    if array.shape == target.shape:
        return array
    image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), mode="L")
    resized = image.resize((target.shape[1], target.shape[0]), Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32)


class TemplateRecognizer:
    def __init__(self) -> None:
        if not TEMPLATE_MANIFEST_PATH.exists():
            raise FileNotFoundError(
                "Template manifest not found. Run `python -m src.main calibrate --bootstrap-templates` first."
            )

        manifest = json.loads(TEMPLATE_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.board_bottom = manifest["board_bottom"]
        self.empty_templates = {
            key: _load_gray_template(value)
            for key, value in manifest["empty_templates"].items()
        }
        self.piece_templates = {
            symbol: _load_gray_template(filename)
            for symbol, filename in manifest["pieces"].items()
        }

    def _cell_diff(self, cell_array: np.ndarray, background: np.ndarray) -> np.ndarray:
        return np.abs(cell_array - background)

    def _classify_cell(self, row: int, col: int, cell: Image.Image) -> str | None:
        color = _square_color(row, col, self.board_bottom)
        background = self.empty_templates[color]
        cell_array = _resize_to_match(image_to_gray_array(cell), background)
        diff = self._cell_diff(cell_array, background)

        empty_score = float(np.mean(diff))
        signal_strength = float(np.percentile(diff, 90))
        if empty_score < EMPTY_SCORE_THRESHOLD and signal_strength < MIN_PIECE_SIGNAL:
            return None

        best_symbol: str | None = None
        best_score = float("inf")
        for symbol, template in self.piece_templates.items():
            normalized_template = _resize_to_match(template, diff)
            score = float(np.mean(np.abs(diff - normalized_template)))
            if score < best_score:
                best_score = score
                best_symbol = symbol

        return best_symbol

    def recognize(self, board_image: Image.Image) -> RecognitionResult:
        board = chess.Board(None)
        occupied_count = 0

        for row, col, cell in iter_cells(board_image):
            symbol = self._classify_cell(row, col, cell)
            if not symbol:
                continue
            square = _screen_cell_to_square(row, col, self.board_bottom)
            board.set_piece_at(square, chess.Piece.from_symbol(symbol))
            occupied_count += 1

        return RecognitionResult(board_fen=board.board_fen(), occupied_count=occupied_count)


def capture_snapshot(board_image: Image.Image, board_bottom: str) -> BoardSnapshot:
    cells: dict[chess.Square, np.ndarray] = {}
    for row, col, cell in iter_cells(board_image):
        square = _screen_cell_to_square(row, col, board_bottom)
        cells[square] = image_to_gray_array(cell)
    return BoardSnapshot(cells=cells)


def square_diff_scores(
    previous: BoardSnapshot,
    current: BoardSnapshot,
) -> dict[chess.Square, float]:
    scores: dict[chess.Square, float] = {}
    for square, prev_array in previous.cells.items():
        curr_array = _resize_to_match(current.cells[square], prev_array)
        prev_array = _resize_to_match(prev_array, curr_array)
        scores[square] = float(np.mean(np.abs(prev_array - curr_array)))
    return scores


def move_changed_squares(board: chess.Board, move: chess.Move) -> set[chess.Square]:
    changed = {move.from_square, move.to_square}

    if board.is_castling(move):
        if chess.square_file(move.to_square) == 6:
            rook_from = chess.H1 if board.turn == chess.WHITE else chess.H8
            rook_to = chess.F1 if board.turn == chess.WHITE else chess.F8
        else:
            rook_from = chess.A1 if board.turn == chess.WHITE else chess.A8
            rook_to = chess.D1 if board.turn == chess.WHITE else chess.D8
        changed.update({rook_from, rook_to})

    if board.is_en_passant(move):
        direction = -8 if board.turn == chess.WHITE else 8
        changed.add(move.to_square + direction)

    return changed


def infer_move_from_square_diffs(
    board: chess.Board,
    diff_scores: dict[chess.Square, float],
) -> chess.Move | None:
    if not diff_scores:
        return None

    total_diff = sum(diff_scores.values())
    ranked = sorted(diff_scores.values(), reverse=True)
    if ranked[0] < 3.0:
        return None

    best_move: chess.Move | None = None
    best_score = float("-inf")
    second_best_score = float("-inf")

    for move in board.legal_moves:
        expected = move_changed_squares(board, move)
        expected_sum = sum(diff_scores.get(square, 0.0) for square in expected)
        unexpected_sum = total_diff - expected_sum
        weak_expected = sum(
            1 for square in expected if diff_scores.get(square, 0.0) < 4.0
        )
        score = (expected_sum * 2.0) - unexpected_sum - (weak_expected * 5.0)
        if score > best_score:
            second_best_score = best_score
            best_score = score
            best_move = move
        elif score > second_best_score:
            second_best_score = score

    if best_move is None:
        return None

    if best_score - second_best_score < 2.0:
        return None
    return best_move
