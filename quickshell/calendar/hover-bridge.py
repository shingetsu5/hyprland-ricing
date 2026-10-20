#!/usr/bin/python3
"""Forward Waybar clock hover events to the parent QML process as JSON lines."""
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

runtime = Path(os.environ['XDG_RUNTIME_DIR'])
lock = (runtime / 'waybar-calendar.lock').open('w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit('A calendar hover bridge is already running')
path = runtime / 'waybar-calendar.sock'
path.unlink(missing_ok=True)
sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.bind(str(path))
os.chmod(path, 0o600)

def hypr_json(command):
    return json.loads(subprocess.check_output(['hyprctl', '-j', command], timeout=2))

while True:
    try:
        event, x, y, width, height = sock.recv(512).decode().split()
        message = {'event': event}
        if event == 'enter':
            cursor = hypr_json('cursorpos')
            monitors = hypr_json('monitors')
            monitor = next((m for m in monitors
                if m['x'] <= cursor['x'] < m['x'] + m['width'] / m['scale']
                and m['y'] <= cursor['y'] < m['y'] + m['height'] / m['scale']), None)
            if monitor is None:
                continue
            # GTK geometry is relative to the bar surface. Layer position includes
            # Waybar's configured margins and remains correct on mixed-DPI screens.
            layers = hypr_json('layers').get(monitor['name'], {}).get('levels', {})
            bar = next((layer for group in layers.values() for layer in group
                        if layer.get('namespace') == 'waybar'), None)
            if bar is None:
                continue
            message.update(screen=monitor['name'],
                center=bar['x'] - monitor['x'] + int(x) + int(width) / 2,
                bottom=bar['y'] - monitor['y'] + int(y) + int(height))
        print(json.dumps(message), flush=True)
    except (ValueError, OSError, subprocess.SubprocessError, StopIteration) as error:
        print(f'Calendar bridge: {error}', file=sys.stderr, flush=True)
