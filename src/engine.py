from __future__ import annotations

import chess
import chess.engine

from .config import RuntimeConfig


class EngineWrapper:
    def __init__(self, runtime_config: RuntimeConfig) -> None:
        self.runtime_config = runtime_config
        self.engine = chess.engine.SimpleEngine.popen_uci(runtime_config.stockfish_path)

    def choose_move(self, board: chess.Board) -> chess.Move:
        result = self.engine.play(
            board,
            chess.engine.Limit(time=self.runtime_config.think_time),
        )
        if result.move not in board.legal_moves:
            raise RuntimeError("Engine returned an illegal move.")
        return result.move

    def close(self) -> None:
        self.engine.quit()
