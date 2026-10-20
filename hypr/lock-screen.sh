#!/bin/sh
# Keep one lock request active and send output to the user journal.
set -eu
exec 9>"${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hyprlock-launch.lock"
flock -n 9 || exit 0
# Preserve the previous swaylock-effects two-second grace period.
exec systemd-cat --identifier=hyprlock /usr/bin/hyprlock --grace 2 "$@"
