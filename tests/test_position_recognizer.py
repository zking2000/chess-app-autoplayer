import unittest

import chess

from src.position_recognizer import infer_move_from_square_diffs, move_changed_squares


class PositionRecognizerTests(unittest.TestCase):
    def test_move_changed_squares_for_castling(self) -> None:
        board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")

        changed = move_changed_squares(board, chess.Move.from_uci("e1g1"))

        self.assertEqual(
            changed,
            {
                chess.parse_square("e1"),
                chess.parse_square("g1"),
                chess.parse_square("h1"),
                chess.parse_square("f1"),
            },
        )

    def test_infer_move_from_square_diffs_prefers_matching_move(self) -> None:
        board = chess.Board()
        diff_scores = {square: 0.1 for square in chess.SQUARES}
        diff_scores[chess.parse_square("e2")] = 25.0
        diff_scores[chess.parse_square("e4")] = 28.0

        move = infer_move_from_square_diffs(board, diff_scores)

        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "e2e4")


if __name__ == "__main__":
    unittest.main()
