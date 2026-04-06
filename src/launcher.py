from __future__ import annotations

import subprocess
import time

from PIL import ImageGrab
import pyautogui


def launch_and_focus_app(app_name: str = "Chess", settle_seconds: float = 1.0) -> None:
    subprocess.run(["open", "-a", app_name], check=True)
    script = f'tell application "{app_name}" to activate'
    subprocess.run(["osascript", "-e", script], check=True)
    time.sleep(settle_seconds)


def run_self_check(app_name: str = "Chess") -> list[str]:
    messages: list[str] = []
    launch_and_focus_app(app_name)
    messages.append(f"Launched and focused {app_name}.app")

    try:
        ImageGrab.grab()
        messages.append("Screen Recording check passed.")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Screenshot failed. Please grant Screen Recording permission."
        ) from exc

    try:
        pyautogui.position()
        pyautogui.moveRel(0, 0, duration=0)
        messages.append("Accessibility check passed.")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Accessibility API call failed. Please grant Accessibility permission."
        ) from exc

    return messages
