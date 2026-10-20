#!/bin/sh
# Scope Super+Space to the app launcher; keep the calendar and power menu alive.
config="$HOME/.config/quickshell/shell.qml"
if quickshell ipc -p "$config" show >/dev/null 2>&1; then
    quickshell kill -p "$config"
else
    env -u GTK_THEME QT_QPA_PLATFORM=wayland QT_QPA_PLATFORMTHEME=xdgdesktopportal quickshell -p "$config" --no-duplicate --daemonize
fi
