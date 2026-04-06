import unittest

import chess

from src.game_state import infer_move_from_observation, validate_initial_observation


class GameStateTests(unittest.TestCase):
    def test_infer_move_from_observation_matches_single_legal_move(self) -> None:
        board = chess.Board()
        target = board.copy(stack=False)
        target.push(chess.Move.from_uci("e2e4"))

        move = infer_move_from_observation(board, target.board_fen())

        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "e2e4")

    def test_validate_initial_observation_rejects_non_initial_board(self) -> None:
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))

        with self.assertRaises(RuntimeError):
            validate_initial_observation(board.board_fen())


if __name__ == "__main__":
    unittest.main()
