#!/bin/sh
# Portals need a graphical session target to publish the system colour scheme.
dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP DISPLAY
systemctl --user set-environment QT_QPA_PLATFORMTHEME=xdgdesktopportal
systemctl --user start quickshell-desktop-session.target
systemctl --user start xdg-desktop-portal-gtk.service xdg-desktop-portal.service
if ! /usr/bin/python3 "$HOME/.config/appearance/theme-switch.py" --restore; then
    printf 'Could not restore the desktop theme; continuing with the saved palette\n' >&2
fi
