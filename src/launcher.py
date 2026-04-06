from __future__ import annotations

import subprocess
import time

from PIL import ImageGrab
import pyautogui


def launch_and_focus_app(app_name: str = "Chess", settle_seconds: float = 1.0) -> None:
    script = f'''
if application "{app_name}" is running then
    tell application "{app_name}" to activate
else
    tell application "{app_name}" to launch
end if
'''
    subprocess.run(["osascript", "-e", script], check=True)
    time.sleep(settle_seconds)


def ensure_single_app_window(
    app_name: str = "Chess", settle_seconds: float = 0.5
) -> None:
    script = f'''
if application "{app_name}" is not running then
    return
end if

tell application "{app_name}" to activate

tell application "System Events"
    tell process "{app_name}"
        set windowCount to count windows
        if windowCount is less than or equal to 1 then
            return
        end if

        repeat with i from windowCount to 2 by -1
            try
                click button 1 of window i
            end try
        end repeat
    end tell
end tell
'''
    subprocess.run(["osascript", "-e", script], check=True)
    time.sleep(settle_seconds)


def run_self_check(app_name: str = "Chess") -> list[str]:
    messages: list[str] = []
    launch_and_focus_app(app_name)
    ensure_single_app_window(app_name)
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
