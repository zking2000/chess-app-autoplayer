from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path

import chess
import chess.pgn

from .actuator import play_move
from .ax_board import infer_move_from_piece_maps, read_piece_map  # noqa: F401 (used via _wait_for_opponent_move)
from .calibrate import calibrate_and_optionally_bootstrap
from .config import ROOT_DIR, RuntimeConfig, ensure_directories, load_calibration
from .engine import EngineWrapper
from .launcher import launch_and_focus_app, run_self_check

GAMES_DIR = ROOT_DIR / "state" / "games"
STATS_PATH = ROOT_DIR / "state" / "stats.json"


def _load_stats() -> dict:
    if STATS_PATH.exists():
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    return {"wins": 0, "losses": 0, "draws": 0, "games": 0}


def _save_stats(stats: dict) -> None:
    STATS_PATH.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def _save_pgn(game: chess.pgn.Game, bot_color: str, result: str) -> Path:
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = GAMES_DIR / f"game_{ts}.pgn"
    with path.open("w", encoding="utf-8") as f:
        print(game, file=f, end="\n")
    return path


def _record_result(result: str, bot_color: str) -> dict:
    stats = _load_stats()
    stats["games"] += 1
    if result == "1-0":
        if bot_color == "white":
            stats["wins"] += 1
        else:
            stats["losses"] += 1
    elif result == "0-1":
        if bot_color == "black":
            stats["wins"] += 1
        else:
            stats["losses"] += 1
    else:
        stats["draws"] += 1
    _save_stats(stats)
    return stats


def _build_runtime_config(args: argparse.Namespace) -> RuntimeConfig:
    return RuntimeConfig(
        think_time=args.think_time,
        poll_interval=args.poll_interval,
        max_recognition_retries=args.max_recognition_retries,
        move_confirmation_timeout=args.move_confirmation_timeout,
        launch_app=not args.no_launch,
    )


def _wait_for_our_move_confirmation(
    move: chess.Move,
    app_name: str,
    runtime: RuntimeConfig,
) -> None:
    """Poll until the source square is cleared, confirming our piece moved."""
    deadline = time.time() + runtime.move_confirmation_timeout
    while time.time() < deadline:
        state = read_piece_map(app_name)
        if state.get(move.from_square) is None:
            return
        time.sleep(runtime.poll_interval)
    raise RuntimeError(
        f"Move confirmation timeout: piece did not leave {chess.square_name(move.from_square)} "
        f"(expected move {move.uci()})."
    )


def _wait_for_opponent_move(
    board: chess.Board,
    app_name: str,
    runtime: RuntimeConfig,
) -> chess.Move:
    """Poll Accessibility API until the opponent's move is detected.

    Compares the live AX board state against the expected state from our
    internal ``board`` object (which already has the bot's last move applied).
    No race condition: we detect the DIFFERENCE between expected and actual.
    """
    from .position_recognizer import move_changed_squares as _mcs

    expected = board.piece_map()
    while True:
        current = read_piece_map(app_name)
        changed = {
            sq
            for sq in set(expected) | set(current)
            if expected.get(sq) != current.get(sq)
        }
        if changed:
            for move in board.legal_moves:
                if _mcs(board, move) == changed:
                    return move
        time.sleep(runtime.poll_interval)


def command_self_check(args: argparse.Namespace) -> int:
    app_name = "Chess"
    for line in run_self_check(app_name):
        print(line)
    return 0


def command_calibrate(args: argparse.Namespace) -> int:
    if not args.no_launch:
        launch_and_focus_app("Chess")

    if args.corners:
        calibration = calibrate_and_optionally_bootstrap(
            bot_color=args.bot_color,
            board_bottom=args.board_bottom,
            bootstrap=args.bootstrap_templates,
            use_corners=True,
        )
        print("4-corner calibration complete, homography saved.")
    else:
        explicit_coords = [args.board_left, args.board_top, args.board_size]
        if any(value is not None for value in explicit_coords) and any(
            value is None for value in explicit_coords
        ):
            raise ValueError("--board-left, --board-top, and --board-size must all be provided together.")

        calibration = calibrate_and_optionally_bootstrap(
            bot_color=args.bot_color,
            board_bottom=args.board_bottom,
            bootstrap=args.bootstrap_templates,
            board_left=args.board_left,
            board_top=args.board_top,
            board_size=args.board_size,
        )

    print(
        f"Board region: left={calibration.board_left}, top={calibration.board_top}, size={calibration.board_size}"
    )
    if args.bootstrap_templates:
        print("Templates generated from current screenshot.")
    return 0


def command_dry_run(args: argparse.Namespace) -> int:
    runtime = _build_runtime_config(args)
    ensure_directories()
    calibration = load_calibration()
    if runtime.launch_app:
        launch_and_focus_app(calibration.app_name)

    board = chess.Board()
    bot_turn = chess.WHITE if calibration.bot_color == "white" else chess.BLACK
    if board.turn != bot_turn:
        print("Not the bot's turn. Let the opponent move first.")
        return 0

    engine = EngineWrapper(runtime)
    try:
        move = engine.choose_move(board)
        print(f"Best move: {move.uci()}")
    finally:
        engine.close()

    return 0


def command_play(args: argparse.Namespace) -> int:
    runtime = _build_runtime_config(args)
    ensure_directories()
    calibration = load_calibration()
    if runtime.launch_app:
        launch_and_focus_app(calibration.app_name)

    app_name = calibration.app_name
    bot_color = calibration.bot_color
    board = chess.Board()
    bot_turn = chess.WHITE if bot_color == "white" else chess.BLACK
    engine = EngineWrapper(runtime)
    half_moves = 0

    # PGN recording
    pgn_game = chess.pgn.Game()
    pgn_game.headers["Event"] = "Chess.app Autoplayer"
    pgn_game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
    pgn_game.headers["White"] = "Stockfish" if bot_color == "white" else "Chess.app AI"
    pgn_game.headers["Black"] = "Chess.app AI" if bot_color == "white" else "Stockfish"
    pgn_node = pgn_game

    try:
        while not board.is_game_over():
            if args.max_half_moves is not None and half_moves >= args.max_half_moves:
                print("Max half-move limit reached, stopping early.")
                break

            if board.turn == bot_turn:
                move = engine.choose_move(board)
                print(f"Bot move: {move.uci()}")
                play_move(calibration, move)
                board.push(move)
                pgn_node = pgn_node.add_variation(move)
                _wait_for_our_move_confirmation(move, app_name, runtime)
                print("  Move confirmed.")
            else:
                print("Waiting for opponent move...")
                opponent_move = _wait_for_opponent_move(board, app_name, runtime)
                print(f"Opponent move: {opponent_move.uci()}")
                board.push(opponent_move)
                pgn_node = pgn_node.add_variation(opponent_move)
                # Allow Chess.app animation to finish before we click again
                time.sleep(1.2)
            half_moves += 1
    finally:
        engine.close()

    result = board.result(claim_draw=True)
    pgn_game.headers["Result"] = result
    print(f"\nGame over: {result}")

    if not args.no_save:
        pgn_path = _save_pgn(pgn_game, bot_color, result)
        print(f"PGN saved: {pgn_path}")
        if not (args.max_half_moves is not None and half_moves >= args.max_half_moves):
            stats = _record_result(result, bot_color)
            print(
                f"Stats — W: {stats['wins']}  L: {stats['losses']}"
                f"  D: {stats['draws']}  Total: {stats['games']}"
            )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chess.app offline autoplayer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    self_check = subparsers.add_parser("self-check", help="Check permissions and basic capabilities")
    self_check.set_defaults(func=command_self_check)

    calibrate = subparsers.add_parser("calibrate", help="Calibrate board region and generate templates")
    calibrate.add_argument("--bot-color", choices=["white", "black"], required=True)
    calibrate.add_argument("--board-bottom", choices=["white", "black"], required=True)
    calibrate.add_argument("--bootstrap-templates", action="store_true")
    calibrate.add_argument("--corners", action="store_true", help="4-corner perspective calibration (recommended for 3D boards)")
    calibrate.add_argument("--board-left", type=int)
    calibrate.add_argument("--board-top", type=int)
    calibrate.add_argument("--board-size", type=int)
    calibrate.add_argument("--no-launch", action="store_true")
    calibrate.set_defaults(func=command_calibrate)

    for name, help_text, handler in [
        ("dry-run", "Print best move only, no clicks", command_dry_run),
        ("play", "Run a full automated game", command_play),
    ]:
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.add_argument("--think-time", type=float, default=0.5)
        subparser.add_argument("--poll-interval", type=float, default=0.5)
        subparser.add_argument("--max-recognition-retries", type=int, default=3)
        subparser.add_argument("--move-confirmation-timeout", type=float, default=10.0)
        subparser.add_argument("--max-half-moves", type=int)
        subparser.add_argument("--no-launch", action="store_true")
        if name == "play":
            subparser.add_argument(
                "--no-save", action="store_true", help="Skip saving PGN and stats"
            )
        subparser.set_defaults(func=handler)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
