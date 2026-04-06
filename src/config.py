from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import ImageGrab
import pyautogui


ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT_DIR / "state"
ASSETS_DIR = ROOT_DIR / "assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
CALIBRATION_PATH = STATE_DIR / "calibration.json"
TEMPLATE_MANIFEST_PATH = TEMPLATES_DIR / "manifest.json"


def _default_stockfish_path() -> str:
    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path:
        return env_path

    candidates = [
        "/opt/homebrew/bin/stockfish",
        "/usr/local/bin/stockfish",
        "/opt/local/bin/stockfish",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return "stockfish"


@dataclass
class Calibration:
    board_left: int
    board_top: int
    board_size: int
    board_bottom: str
    bot_color: str
    app_name: str = "Chess"
    corner_a1: list[int] | None = field(default=None)
    corner_h1: list[int] | None = field(default=None)
    corner_a8: list[int] | None = field(default=None)
    corner_h8: list[int] | None = field(default=None)
    homography: list[list[float]] | None = field(default=None)

    @property
    def square_size(self) -> float:
        return self.board_size / 8.0

    @property
    def board_right(self) -> int:
        return self.board_left + self.board_size

    @property
    def board_bottom_px(self) -> int:
        return self.board_top + self.board_size


@dataclass
class RuntimeConfig:
    think_time: float = 0.5
    poll_interval: float = 0.25
    max_recognition_retries: int = 3
    move_confirmation_timeout: float = 8.0
    stockfish_path: str = _default_stockfish_path()
    launch_app: bool = True


def ensure_directories() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def get_capture_scale() -> tuple[float, float]:
    logical_size = pyautogui.size()
    capture_size = ImageGrab.grab().size
    return (
        capture_size[0] / logical_size.width,
        capture_size[1] / logical_size.height,
    )


def logical_to_capture(x: int, y: int) -> tuple[int, int]:
    scale_x, scale_y = get_capture_scale()
    return int(round(x * scale_x)), int(round(y * scale_y))


def capture_to_logical(x: int, y: int) -> tuple[int, int]:
    scale_x, scale_y = get_capture_scale()
    return int(round(x / scale_x)), int(round(y / scale_y))


def save_calibration(calibration: Calibration) -> None:
    ensure_directories()
    CALIBRATION_PATH.write_text(
        json.dumps(asdict(calibration), indent=2),
        encoding="utf-8",
    )


def load_calibration() -> Calibration:
    if not CALIBRATION_PATH.exists():
        raise FileNotFoundError(
            "calibration.json not found. Run `python -m src.main calibrate` first."
        )
    data: dict[str, Any] = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    _OPTIONAL_FIELDS = ("corner_a1", "corner_h1", "corner_a8", "corner_h8", "homography")
    for key in _OPTIONAL_FIELDS:
        data.setdefault(key, None)
    return Calibration(**data)
