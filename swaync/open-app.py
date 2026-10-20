#!/usr/bin/env python3
"""Open a swaync settings app and place its window in the center."""

import json
import os
import subprocess
import sys
import time


APPS = {
    "network": ("Nm-connection-editor", ["nm-connection-editor"]),
    "bluetooth": ("Blueman-manager", ["blueman-manager"]),
}


def clients():
    result = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True, text=True)
    if result.returncode:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def dispatch(action, *args):
    return subprocess.run(
        ["hyprctl", "dispatch", action, *args],
        capture_output=True,
        text=True,
    ).returncode == 0


def target_window(window_class):
    matches = [window for window in clients() if window.get("class") == window_class]
    return matches[0] if matches else None


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in APPS:
        return 2
    window_class, command = APPS[sys.argv[1]]

    subprocess.run(["swaync-client", "--close-panel"], stdout=subprocess.DEVNULL)
    window = target_window(window_class)
    if window is None:
        env = os.environ.copy()
        subprocess.Popen(
            command,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(60):
            time.sleep(0.1)
            window = target_window(window_class)
            if window is not None:
                break

    if window is None:
        subprocess.Popen(["notify-send", "Не удалось открыть окно настроек"])
        return 1

    address = f"address:{window['address']}"
    actions = (
        ("focuswindow", address),
        ("setfloating", address),
        ("resizewindowpixel", f"exact 900 600,{address}"),
        ("centerwindow", "1"),
    )
    for action, argument in actions:
        if not dispatch(action, argument):
            subprocess.Popen(["notify-send", "Не удалось разместить окно настроек"])
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
