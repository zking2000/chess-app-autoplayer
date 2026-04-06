from __future__ import annotations

from typing import Iterator

import numpy as np
from PIL import Image, ImageGrab

from .config import Calibration


def capture_board(calibration: Calibration) -> Image.Image:
    bbox = (
        calibration.board_left,
        calibration.board_top,
        calibration.board_right,
        calibration.board_bottom_px,
    )
    return ImageGrab.grab(bbox=bbox)


def iter_cells(board_image: Image.Image) -> Iterator[tuple[int, int, Image.Image]]:
    size = board_image.size[0]
    square_size = size / 8.0
    for row in range(8):
        for col in range(8):
            left = int(round(col * square_size))
            top = int(round(row * square_size))
            right = int(round((col + 1) * square_size))
            bottom = int(round((row + 1) * square_size))
            yield row, col, board_image.crop((left, top, right, bottom))


def image_to_gray_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32)
