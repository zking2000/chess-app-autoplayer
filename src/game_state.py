from __future__ import annotations

import chess


def infer_move_from_observation(
    board: chess.Board,
    observed_board_fen: str,
) -> chess.Move | None:
    matches: list[chess.Move] = []
    for move in board.legal_moves:
        candidate = board.copy(stack=False)
        candidate.push(move)
        if candidate.board_fen() == observed_board_fen:
            matches.append(move)

    if len(matches) == 1:
        return matches[0]
    return None


def validate_initial_observation(observed_board_fen: str) -> None:
    initial_board_fen = chess.Board().board_fen()
    if observed_board_fen != initial_board_fen:
        raise RuntimeError(
            "当前截图不是新开局初始局面。第一版需要从新对局开始运行。"
        )
