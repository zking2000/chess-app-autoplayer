"""
Actuator: executes chess moves in Chess.app using macOS Accessibility API.

Chess.app exposes each board square as a button inside a group element.
Button descriptions follow the pattern:
  - occupied square: "<piece_name>, <square>" e.g. "白兵, e2"
  - empty square:    "<square>"               e.g. "e4"

We locate each square by description suffix and press it via AX API.
This approach is robust against 3D perspective rendering – no coordinate
calibration required.
"""
from __future__ import annotations

import subprocess
import time

import chess

from .config import Calibration


_AX_CLICK_SCRIPT = """\
tell application "{app}" to activate
delay 0.4
tell application "System Events"
    tell process "{app}"
        set frontmost to true
        set wins to windows
        if (count of wins) is 0 then return "no_window:{sq}"
        set grp to first group of (item 1 of wins)
        repeat with btn in (every button of grp)
            set desc to description of btn
            if desc is "{sq}" or desc ends with ", {sq}" then
                click btn
                return "ok:" & desc
            end if
        end repeat
        return "not_found:{sq}"
    end tell
end tell
"""


def _square_name(square: chess.Square) -> str:
    return chess.square_name(square)


def _ax_click(square: chess.Square, app_name: str) -> None:
    sq = _square_name(square)
    script = _AX_CLICK_SCRIPT.format(app=app_name, sq=sq)
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = result.stdout.strip()
    if not output.startswith("ok:"):
        raise RuntimeError(
            f"AX click failed (square={sq}): {output or result.stderr.strip()}"
        )


def play_move(
    calibration: Calibration,
    move: chess.Move,
    click_interval: float = 0.5,
) -> None:
    app_name = calibration.app_name
    _ax_click(move.from_square, app_name)
    time.sleep(click_interval)
    _ax_click(move.to_square, app_name)

    if move.promotion == chess.QUEEN:
        time.sleep(click_interval)
        # Promotion: Chess.app shows a dialog; send 'q' to select queen
        subprocess.run(["osascript", "-e", 'tell application "Chess" to activate'], check=True)
        time.sleep(0.3)
        subprocess.run(
            ["cliclick", "kp:q"],
            capture_output=True,
        )


# ── Backward compatibility: square_to_capture / square_to_screen kept for tests ──

import numpy as np
import pyautogui

from .config import capture_to_logical


def square_to_capture(calibration: Calibration, square: chess.Square) -> tuple[int, int]:
    file_idx = chess.square_file(square)
    rank_idx = chess.square_rank(square)

    if calibration.homography is not None:
        H = np.array(calibration.homography)
        p = H @ np.array([file_idx + 0.5, rank_idx + 0.5, 1.0])
        return int(round(p[0] / p[2])), int(round(p[1] / p[2]))

    if calibration.board_bottom == "white":
        col = file_idx
        row = 7 - rank_idx
    else:
        col = 7 - file_idx
        row = rank_idx

    square_size = calibration.square_size
    x = calibration.board_left + int(round((col + 0.5) * square_size))
    y = calibration.board_top + int(round((row + 0.5) * square_size))
    return x, y


def square_to_screen(calibration: Calibration, square: chess.Square) -> tuple[int, int]:
    return capture_to_logical(*square_to_capture(calibration, square))
