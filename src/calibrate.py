from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import chess
import numpy as np
from PIL import Image
import pyautogui

from .board_capture import capture_board, image_to_gray_array, iter_cells
from .config import (
    Calibration,
    TEMPLATE_MANIFEST_PATH,
    TEMPLATES_DIR,
    logical_to_capture,
    save_calibration,
)


def _prompt_mouse_point(label: str) -> tuple[int, int]:
    input(f"Move mouse to {label}, then press Enter...")
    position = pyautogui.position()
    capture_x, capture_y = logical_to_capture(int(position.x), int(position.y))
    print(
        f"Recorded {label}: logical=({position.x}, {position.y}), capture=({capture_x}, {capture_y})"
    )
    return capture_x, capture_y


def run_calibration(
    bot_color: str,
    board_bottom: str,
    board_left: int | None = None,
    board_top: int | None = None,
    board_size: int | None = None,
) -> Calibration:
    if board_left is not None and board_top is not None and board_size is not None:
        left = board_left
        top = board_top
        right = board_left + board_size
        bottom = board_top + board_size
    else:
        left, top = _prompt_mouse_point("the top-left corner of the board")
        right, bottom = _prompt_mouse_point("the bottom-right corner of the board")

    board_size = min(right - left, bottom - top)
    if board_size <= 0:
        raise ValueError("Calibration failed: board size must be greater than 0.")

    calibration = Calibration(
        board_left=left,
        board_top=top,
        board_size=board_size,
        board_bottom=board_bottom,
        bot_color=bot_color,
    )
    save_calibration(calibration)
    return calibration


def _square_color(row: int, col: int, board_bottom: str) -> str:
    if board_bottom == "white":
        is_light = (row + col) % 2 == 1
    else:
        is_light = (row + col) % 2 == 0
    return "light" if is_light else "dark"


def _piece_square_map_for_bootstrap(board_bottom: str) -> dict[tuple[int, int], str]:
    layout = chess.Board()
    result: dict[tuple[int, int], str] = {}
    for square, piece in layout.piece_map().items():
        rank = chess.square_rank(square)
        file_idx = chess.square_file(square)

        if board_bottom == "white":
            row = 7 - rank
            col = file_idx
        else:
            row = rank
            col = 7 - file_idx

        result[(row, col)] = piece.symbol()
    return result


def _save_array_as_png(array: np.ndarray, path: Path) -> None:
    clipped = np.clip(array, 0, 255).astype(np.uint8)
    Image.fromarray(clipped, mode="L").save(path)


def _resize_array(array: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    if array.shape == target_shape:
        return array
    image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), mode="L")
    resized = image.resize((target_shape[1], target_shape[0]), Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32)


def _average_arrays(arrays: Iterable[np.ndarray]) -> np.ndarray:
    array_list = list(arrays)
    target_shape = array_list[0].shape
    normalized = [_resize_array(array, target_shape) for array in array_list]
    stack = np.stack(normalized, axis=0)
    return np.mean(stack, axis=0)


def bootstrap_templates(board_image: Image.Image, board_bottom: str) -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    empty_samples: dict[str, list[np.ndarray]] = {"light": [], "dark": []}
    piece_samples: dict[str, list[np.ndarray]] = {}
    occupied = _piece_square_map_for_bootstrap(board_bottom)

    for row, col, cell in iter_cells(board_image):
        color = _square_color(row, col, board_bottom)
        gray = image_to_gray_array(cell)
        if (row, col) in occupied:
            piece_samples.setdefault(occupied[(row, col)], []).append(gray)
        else:
            empty_samples[color].append(gray)

    if not empty_samples["light"] or not empty_samples["dark"]:
        raise RuntimeError("Failed to collect empty square templates from the initial position.")

    empty_light = _average_arrays(empty_samples["light"])
    empty_dark = _average_arrays(empty_samples["dark"])
    _save_array_as_png(empty_light, TEMPLATES_DIR / "empty_light.png")
    _save_array_as_png(empty_dark, TEMPLATES_DIR / "empty_dark.png")

    manifest = {
        "board_bottom": board_bottom,
        "empty_templates": {
            "light": "empty_light.png",
            "dark": "empty_dark.png",
        },
        "pieces": {},
    }

    for piece_symbol, samples in piece_samples.items():
        diffs: list[np.ndarray] = []
        for sample in samples:
            normalized_light = _resize_array(empty_light, sample.shape)
            normalized_dark = _resize_array(empty_dark, sample.shape)
            origin_color = (
                "light"
                if np.mean(np.abs(sample - normalized_light))
                < np.mean(np.abs(sample - normalized_dark))
                else "dark"
            )
            background = normalized_light if origin_color == "light" else normalized_dark
            diffs.append(np.abs(sample - background))

        averaged_diff = _average_arrays(diffs)
        filename = f"piece_{piece_symbol}.png"
        _save_array_as_png(averaged_diff, TEMPLATES_DIR / filename)
        manifest["pieces"][piece_symbol] = filename

    TEMPLATE_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def _compute_homography(corners: list[tuple[int, int]]) -> list[list[float]]:
    """DLT 4-point homography: maps (file+0.5, rank+0.5) -> capture (x, y).

    corners: [a1, h1, a8, h8] as (capture_x, capture_y) tuples.
    """
    src = np.array(
        [
            [0.5, 0.5],
            [7.5, 0.5],
            [0.5, 7.5],
            [7.5, 7.5],
        ],
        dtype=np.float64,
    )
    dst = np.array(corners, dtype=np.float64)

    A = []
    for (x, y), (X, Y) in zip(src, dst):
        A.append([-x, -y, -1, 0, 0, 0, X * x, X * y, X])
        A.append([0, 0, 0, -x, -y, -1, Y * x, Y * y, Y])
    A_np = np.array(A)
    _, _, Vt = np.linalg.svd(A_np)
    H = Vt[-1].reshape(3, 3)
    H = H / H[2, 2]
    return H.tolist()


def run_corner_calibration(bot_color: str, board_bottom: str) -> Calibration:
    print("\n=== 4-Corner Perspective Calibration ===")
    print("Chess.app uses a 3D perspective board; 4-corner calibration removes distortion.")
    print("Move the mouse to the center of each corner square, then press Enter.")
    print("Note: Chess.app window must be fully visible and unobscured.\n")

    a1 = _prompt_mouse_point("a1 center (white-bottom: bottom-left)")
    h1 = _prompt_mouse_point("h1 center (white-bottom: bottom-right)")
    a8 = _prompt_mouse_point("a8 center (white-bottom: top-left)")
    h8 = _prompt_mouse_point("h8 center (white-bottom: top-right)")

    corners = [a1, h1, a8, h8]
    homography = _compute_homography(corners)

    all_x = [c[0] for c in corners]
    all_y = [c[1] for c in corners]
    board_left = min(all_x)
    board_top = min(all_y)
    board_size = max(max(all_x) - min(all_x), max(all_y) - min(all_y))

    calibration = Calibration(
        board_left=board_left,
        board_top=board_top,
        board_size=board_size,
        board_bottom=board_bottom,
        bot_color=bot_color,
        corner_a1=list(a1),
        corner_h1=list(h1),
        corner_a8=list(a8),
        corner_h8=list(h8),
        homography=homography,
    )
    save_calibration(calibration)
    return calibration


def calibrate_and_optionally_bootstrap(
    bot_color: str,
    board_bottom: str,
    bootstrap: bool,
    board_left: int | None = None,
    board_top: int | None = None,
    board_size: int | None = None,
    use_corners: bool = False,
) -> Calibration:
    if use_corners:
        calibration = run_corner_calibration(bot_color=bot_color, board_bottom=board_bottom)
    else:
        calibration = run_calibration(
            bot_color=bot_color,
            board_bottom=board_bottom,
            board_left=board_left,
            board_top=board_top,
            board_size=board_size,
        )
    if bootstrap:
        board_image = capture_board(calibration)
        bootstrap_templates(board_image, board_bottom=board_bottom)
    return calibration
