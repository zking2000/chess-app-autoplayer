"""
Actuator: executes chess moves in Chess.app using macOS Accessibility API.

Chess.app exposes each board square as a button inside a group element.
Button descriptions follow the pattern:
  - occupied square: "<piece_name>, <square>" e.g. "White Pawn, e2"
  - empty square:    "<square>"               e.g. "e4"

We locate each square by description suffix and press it via AX API.
This approach is robust against 3D perspective rendering – no coordinate
calibration required.

Retry strategy
--------------
Chess.app temporarily hides its Accessibility window during piece animations.
To handle this, both the AppleScript (inner loop) and the Python caller
(_ax_click / play_move) implement independent retry layers:

  Layer 1 – AppleScript: polls `windows` up to 15× (≈4.5 s) before giving up.
  Layer 2 – Python _ax_click: retries the full AppleScript up to MAX_CLICK_RETRIES
             times with a wait between each attempt.
  Layer 3 – Python play_move: retries the entire from→to click sequence up to
             MAX_MOVE_RETRIES times, so a partial selection is never left stuck.
"""
from __future__ import annotations

import subprocess
import time

import chess

from .config import Calibration

MAX_CLICK_RETRIES = 4   # attempts per individual square click
CLICK_RETRY_DELAY = 1.2 # seconds between click-level retries
MAX_MOVE_RETRIES  = 3   # attempts for the full from→to sequence
MOVE_RETRY_DELAY  = 2.0 # seconds between move-level retries

_AX_CLICK_SCRIPT = """\
tell application "{app}" to activate
delay 0.8
tell application "System Events"
    tell process "{app}"
        set frontmost to true
        set retries to 0
        repeat
            set wins to windows
            if (count of wins) > 0 then exit repeat
            delay 0.3
            set retries to retries + 1
            if retries > 15 then return "no_window:{sq}"
        end repeat
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
    """Click a board square via Accessibility API, with Python-level retries."""
    sq = _square_name(square)
    script = _AX_CLICK_SCRIPT.format(app=app_name, sq=sq)
    last_error = ""

    for attempt in range(MAX_CLICK_RETRIES):
        if attempt > 0:
            print(f"    [click retry {attempt}/{MAX_CLICK_RETRIES - 1}] square={sq}, last={last_error!r}")
            time.sleep(CLICK_RETRY_DELAY)

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            last_error = "osascript timeout"
            continue

        output = result.stdout.strip()
        if output.startswith("ok:"):
            return
        last_error = output or result.stderr.strip()

    raise RuntimeError(
        f"AX click failed after {MAX_CLICK_RETRIES} attempts "
        f"(square={sq}): {last_error}"
    )


def play_move(
    calibration: Calibration,
    move: chess.Move,
    click_interval: float = 0.5,
) -> None:
    """Execute a chess move in Chess.app, with full from→to retry on failure."""
    app_name = calibration.app_name
    last_exc: Exception | None = None

    for attempt in range(MAX_MOVE_RETRIES):
        if attempt > 0:
            print(f"  [move retry {attempt}/{MAX_MOVE_RETRIES - 1}] {move.uci()}, last={last_exc}")
            time.sleep(MOVE_RETRY_DELAY)

        try:
            _ax_click(move.from_square, app_name)
            time.sleep(click_interval)
            _ax_click(move.to_square, app_name)

            if move.promotion == chess.QUEEN:
                time.sleep(click_interval)
                # Promotion: Chess.app shows a dialog; send 'q' to select queen
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app_name}" to activate'],
                    check=True,
                )
                time.sleep(0.3)
                subprocess.run(["cliclick", "kp:q"], capture_output=True)
            return  # success

        except (RuntimeError, subprocess.SubprocessError) as exc:
            last_exc = exc

    raise RuntimeError(
        f"play_move failed after {MAX_MOVE_RETRIES} attempts for {move.uci()}: {last_exc}"
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
