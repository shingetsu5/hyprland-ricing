#!/usr/bin/env bash
set -euo pipefail
waybar_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
temporary=$(mktemp "$waybar_dir/libclock-hover.so.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
cc -shared -fPIC -O2 -Wall -Wextra "$waybar_dir/clock-hover.c" -o "$temporary"
chmod 755 "$temporary"
mv -f -- "$temporary" "$waybar_dir/libclock-hover.so"
