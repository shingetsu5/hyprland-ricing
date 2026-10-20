#!/usr/bin/env bash
set -o pipefail

# Allow only one region selection at a time.
runtime=${XDG_RUNTIME_DIR:-/tmp}
exec 9>"$runtime/hypr-screenshot.lock"
flock -n 9 || exit 0

freeze_pid=
image=
unfreeze() {
    if [[ -n $freeze_pid ]]; then
        kill "$freeze_pid" 2>/dev/null || true
        wait "$freeze_pid" 2>/dev/null || true
        freeze_pid=
    fi
}
cleanup() {
    unfreeze
    [[ -z $image ]] || rm -f -- "$image"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

# Wait for compositor layers instead of relying on a fixed rendering delay.
wait_for_layers() {
    python3 - "$1" "$freeze_pid" <<'PY'
import json
import subprocess
import sys
import time

mode, pid = sys.argv[1], int(sys.argv[2])
for _ in range(100):
    try:
        layers = json.loads(subprocess.check_output(
            ['hyprctl', '-j', 'layers'], timeout=1))
        screens = [[layer for group in output.get('levels', {}).values() for layer in group]
                   for output in layers.values()]
        if mode == 'frozen':
            ready = screens and all(any(layer.get('pid') == pid
                and layer.get('alpha', 0) >= .99 for layer in screen) for screen in screens)
        else:
            ready = not any(layer.get('namespace') == 'selection'
                            for screen in screens for layer in screen)
        if ready:
            sys.exit(0)
    except (ValueError, OSError, subprocess.SubprocessError):
        pass
    time.sleep(.02)
sys.exit(1)
PY
}

# Freeze every monitor; disable the colour preview and magnifying lens.
hyprpicker --render-inactive --no-zoom --disable-preview --quiet >/dev/null 2>&1 9>&- &
freeze_pid=$!
wait_for_layers frozen || exit 1
kill -0 "$freeze_pid" 2>/dev/null || exit 1

region=$(slurp -d 9>&-) || exit 0
[[ -n $region ]] || exit 0

# Keep the frozen image until the selection overlay has fully disappeared.
wait_for_layers selected || exit 1
image=$(mktemp "$runtime/hypr-screenshot-XXXXXX.png") || exit 1
grim -g "$region" "$image" 9>&- || exit 1
unfreeze
flock -u 9
swappy -f "$image" 9>&-
