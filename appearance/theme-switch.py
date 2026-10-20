#!/usr/bin/python3
"""Apply one persisted system colour scheme to GTK, portals and the desktop UI."""
import configparser
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import gi
from gi.repository import Gio, GLib

CONFIG = Path.home() / '.config'
settings = Gio.Settings.new('org.gnome.desktop.interface')

def light():
    return settings.get_string('color-scheme') == 'prefer-light'

def emit(*args):
    print(json.dumps({'light': light()}), flush=True)

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.new')
    temp.write_text(text)
    temp.replace(path)

def run(args):
    result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        print(f'{args[0]}: {result.stderr.strip()}', file=sys.stderr)
    return result.returncode == 0

def apply(mode):
    is_light = mode == 'light'
    preferences_file = CONFIG / 'appearance/preferences.json'
    preferences = json.loads(preferences_file.read_text()) if preferences_file.exists() else {}
    replace_cursor = preferences.get('replace_cursor', True)
    theme = 'Flat-Remix-GTK-Blue-' + ('Light' if is_light else 'Dark')
    icons = 'Flat-Remix-Blue-' + ('Light' if is_light else 'Dark')
    theme_roots = [Path.home() / '.themes',
                   Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'themes',
                   Path('/usr/local/share/themes'), Path('/usr/share/themes')]
    if not any((root / theme).is_dir() for root in theme_roots):
        raise RuntimeError(f'GTK theme is not installed: {theme}')
    # GTK3/GTK4 applications outside a full desktop session also read these files.
    for version in ('gtk-3.0', 'gtk-4.0'):
        path = CONFIG / version / 'settings.ini'
        ini = configparser.ConfigParser(interpolation=None)
        ini.read(path)
        if not ini.has_section('Settings'):
            ini.add_section('Settings')
        ini['Settings']['gtk-theme-name'] = theme
        ini['Settings']['gtk-icon-theme-name'] = icons
        if replace_cursor:
            ini['Settings']['gtk-cursor-theme-name'] = 'Bibata-Modern-Ice'
        ini['Settings']['gtk-application-prefer-dark-theme'] = str(not is_light).lower()
        import io
        output = io.StringIO(); ini.write(output)
        write(path, output.getvalue())
    values = {
        'surface': '#ffffff' if is_light else '#20242d',
        'surface_alt': '#edf1f6' if is_light else '#2c3340',
        'text': '#292929' if is_light else '#e7ebf3',
        'muted': '#68747d' if is_light else '#a1aabb',
        'accent': '#429bee' if is_light else '#8ac0f2',
        'battery': '#4a7d4a' if is_light else '#9bd5a3',
        'danger': '#c70e0e' if is_light else '#f38b9a',
        'border': '#d9e0e5' if is_light else '#424b5b',
    }
    # Waybar has a separate, quieter dark palette; other windows keep theirs.
    waybar_values = dict(values)
    waybar_values['mic'] = '#cc60ec' if is_light else '#b4a8ba'
    if not is_light:
        waybar_values.update(surface='#30363b', surface_alt='#3b4349',
            text='#c5cccf', muted='#a2acb2', accent='#98afbc',
            battery='#a8b8a6', danger='#c99a9e', border='#49535b')
    colors = ''.join(f'@define-color desktop_{key} {value};\n'
                     for key, value in values.items())
    colors += ''.join(f'@define-color waybar_{key} {value};\n'
                      for key, value in waybar_values.items())
    write(CONFIG / 'appearance/colors.css', colors)
    settings.delay()
    settings.set_string('gtk-theme', theme)
    settings.set_string('icon-theme', icons)
    if replace_cursor:
        settings.set_string('cursor-theme', 'Bibata-Modern-Ice')
    settings.set_string('color-scheme', 'prefer-light' if is_light else 'prefer-dark')
    settings.apply()
    Gio.Settings.sync()
    run(['pkill', '-USR2', '-x', 'waybar'])
    run(['swaync-client', '--reload-css'])
    emit()

if len(sys.argv) == 2 and sys.argv[1] == '--watch':
    settings.connect('changed::color-scheme', emit)
    emit()
    GLib.MainLoop().run()
elif len(sys.argv) == 2 and sys.argv[1] in ('light', 'dark', '--restore'):
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    with (runtime / 'desktop-theme.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        apply(('light' if light() else 'dark') if sys.argv[1] == '--restore' else sys.argv[1])
else:
    sys.exit('Usage: theme-switch.py light|dark|--restore|--watch')
