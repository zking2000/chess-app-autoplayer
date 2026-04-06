import unittest

import chess
import numpy as np

from src.actuator import square_to_capture
from src.config import Calibration
from src.calibrate import _compute_homography


def _make_calibration_with_corners(
    a1: tuple[int, int],
    h1: tuple[int, int],
    a8: tuple[int, int],
    h8: tuple[int, int],
) -> Calibration:
    corners = [a1, h1, a8, h8]
    H = _compute_homography(corners)
    all_x = [c[0] for c in corners]
    all_y = [c[1] for c in corners]
    return Calibration(
        board_left=min(all_x),
        board_top=min(all_y),
        board_size=max(max(all_x) - min(all_x), max(all_y) - min(all_y)),
        board_bottom="white",
        bot_color="white",
        corner_a1=list(a1),
        corner_h1=list(h1),
        corner_a8=list(a8),
        corner_h8=list(h8),
        homography=H,
    )


class ActuatorTests(unittest.TestCase):
    def test_square_to_capture_with_white_bottom(self) -> None:
        calibration = Calibration(
            board_left=100,
            board_top=200,
            board_size=800,
            board_bottom="white",
            bot_color="white",
        )

        self.assertEqual(square_to_capture(calibration, chess.parse_square("a8")), (150, 250))
        self.assertEqual(square_to_capture(calibration, chess.parse_square("h1")), (850, 950))

    def test_square_to_capture_with_black_bottom(self) -> None:
        calibration = Calibration(
            board_left=100,
            board_top=200,
            board_size=800,
            board_bottom="black",
            bot_color="black",
        )

        self.assertEqual(square_to_capture(calibration, chess.parse_square("h1")), (150, 250))
        self.assertEqual(square_to_capture(calibration, chess.parse_square("a8")), (850, 950))

    def test_square_to_capture_with_homography_identity_grid(self) -> None:
        """Homography on a perfect 8x8 grid should reproduce linear mapping."""
        # Use an axis-aligned perfect grid: each cell is 100x100 capture pixels
        # a1 center = (50, 750), h1 = (750, 750), a8 = (50, 50), h8 = (750, 50)
        cal = _make_calibration_with_corners(
            a1=(50, 750),
            h1=(750, 750),
            a8=(50, 50),
            h8=(750, 50),
        )

        # a1 = file=0, rank=0 -> (50, 750)
        cx, cy = square_to_capture(cal, chess.parse_square("a1"))
        self.assertAlmostEqual(cx, 50, delta=2)
        self.assertAlmostEqual(cy, 750, delta=2)

        # h8 = file=7, rank=7 -> (750, 50)
        cx, cy = square_to_capture(cal, chess.parse_square("h8"))
        self.assertAlmostEqual(cx, 750, delta=2)
        self.assertAlmostEqual(cy, 50, delta=2)

        # e4 = file=4, rank=3
        # With 8 centers from 50..750 step 100: e=index 4 -> 450
        # Rank 3: from top-to-bottom rank 7 at y=50, rank 0 at y=750 -> rank 3 at y=450
        cx, cy = square_to_capture(cal, chess.parse_square("e4"))
        self.assertAlmostEqual(cx, 450, delta=2)
        self.assertAlmostEqual(cy, 450, delta=2)


if __name__ == "__main__":
    unittest.main()
