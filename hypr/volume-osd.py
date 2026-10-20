#!/usr/bin/env python3
"""Show one short volume popup whenever the default audio output changes."""

import fcntl
import os
import re
import subprocess
import time


def volume_state():
    result = subprocess.run(
        ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Volume:\s*([0-9.]+)", result.stdout)
    if result.returncode or not match:
        return None
    percent = max(0, min(100, round(float(match.group(1)) * 100)))
    return percent, "[MUTED]" in result.stdout


def show_volume(state, previous_id):
    percent, muted = state
    icon = (
        "audio-volume-muted-symbolic" if muted else
        "audio-volume-low-symbolic" if percent < 34 else
        "audio-volume-medium-symbolic" if percent < 67 else
        "audio-volume-high-symbolic"
    )
    command = [
        "notify-send", "--print-id", "--transient", "--urgency=low",
        "--expire-time=1500", "--app-name=Громкость", f"--icon={icon}",
        f"--hint=int:value:{0 if muted else percent}",
        "--hint=string:x-canonical-private-synchronous:volume",
    ]
    if previous_id:
        command.append(f"--replace-id={previous_id}")
    command.extend(["Звук выключен" if muted else "Громкость", f"{percent}%"])
    result = subprocess.run(command, capture_output=True, text=True)
    return int(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip().isdigit() else None


def main():
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/tmp/volume-osd-{os.getuid()}")
    with open(os.path.join(runtime, "hypr-volume-osd.lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return

        last_state = volume_state()
        notification_id = None
        while True:
            with subprocess.Popen(
                ["pactl", "subscribe"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            ) as events:
                for _ in events.stdout:
                    state = volume_state()
                    if state is not None and state != last_state:
                        last_state = state
                        notification_id = show_volume(state, notification_id)
            time.sleep(1)


if __name__ == "__main__":
    main()
