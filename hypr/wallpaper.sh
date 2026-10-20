#!/usr/bin/env bash
set -euo pipefail

wallpaper_dir=$(python3 - <<'CONFIG'
import json
from pathlib import Path
path = Path.home() / '.config/appearance/preferences.json'
preferences = json.loads(path.read_text()) if path.exists() else {}
print(preferences.get('wallpaper_dir', str(Path.home() / 'Pictures/wallpapers')))
CONFIG
)
state_file="$HOME/.config/hypr/current-wallpaper"
default_wallpaper="$wallpaper_dir/moonlit-forest-4k.png"

# Arch ships awww, the maintained successor of swww. Older systems can use swww.
if command -v awww >/dev/null 2>&1; then
    wallpaper_client=awww
    wallpaper_daemon=awww-daemon
elif command -v swww >/dev/null 2>&1; then
    wallpaper_client=swww
    wallpaper_daemon=swww-daemon
else
    printf 'Install awww (or swww) to manage wallpapers\n' >&2
    exit 1
fi

start_daemon() {
    if "$wallpaper_client" query >/dev/null 2>&1; then
        return
    fi

    "$wallpaper_daemon" --quiet >/dev/null 2>&1 &
    for _ in {1..50}; do
        if "$wallpaper_client" query >/dev/null 2>&1; then
            return
        fi
        sleep 0.1
    done
    printf 'Wallpaper daemon did not become ready\n' >&2
    return 1
}

case "${1:-start}" in
    start)
        selected="$default_wallpaper"
        if [[ -s "$state_file" ]]; then
            IFS= read -r saved < "$state_file" || true
            if [[ -f "${saved:-}" ]]; then
                selected="$saved"
            fi
        fi
        if [[ ! -f "$selected" ]]; then
            selected=$(find "$wallpaper_dir" -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) -print -quit 2>/dev/null || true)
        fi
        if [[ ! -f "$selected" ]]; then
            printf 'No wallpaper selected; keeping the existing background\n' >&2
            exit 0
        fi
        start_daemon
        "$wallpaper_client" img --resize crop --transition-type none "$selected"
        ;;
    set)
        [[ $# -eq 2 ]] || { printf 'Usage: %s set IMAGE\n' "$0" >&2; exit 2; }
        selected="$(realpath -e -- "$2")"
        allowed_dir="$(realpath -e -- "$wallpaper_dir")"
        [[ "$selected" == "$allowed_dir/"* && -f "$selected" ]] || {
            printf 'Wallpaper must be an image from %s\n' "$allowed_dir" >&2
            exit 2
        }
        start_daemon
        "$wallpaper_client" img --resize crop --transition-type fade --transition-duration 0.8 --transition-fps 60 "$selected"
        temp_state="$(mktemp "$state_file.XXXXXX")"
        printf '%s\n' "$selected" > "$temp_state"
        mv -f -- "$temp_state" "$state_file"
        ;;
    *)
        printf 'Usage: %s start|set IMAGE\n' "$0" >&2
        exit 2
        ;;
esac
