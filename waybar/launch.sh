#!/bin/sh
set -eu
waybar_dir="$HOME/.config/waybar"
if [ ! -f "$waybar_dir/libclock-hover.so" ] || [ "$waybar_dir/clock-hover.c" -nt "$waybar_dir/libclock-hover.so" ]; then
    "$waybar_dir/scripts/build-clock-hover.sh"
fi
# Run the calendar independently from the existing Quickshell app launcher.
QT_QPA_PLATFORM=wayland quickshell -p "$HOME/.config/quickshell/calendar" --no-duplicate --daemonize
pkill -x waybar 2>/dev/null || true
sleep 0.2
exec env -u GTK_THEME QT_QPA_PLATFORMTHEME=xdgdesktopportal GDK_BACKEND=wayland GTK_MODULES="$HOME/.config/waybar/libclock-hover.so${GTK_MODULES:+:$GTK_MODULES}" waybar
