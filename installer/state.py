#!/usr/bin/env python3
"""Installation receipts: package inventory, previous settings and deployment ownership."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess

SERVICES = ('bluetooth.service', 'NetworkManager.service', 'power-profiles-daemon.service',
            'tuned.service', 'tuned-ppd.service', 'sddm.service')
SETTINGS = ('gtk-theme', 'icon-theme', 'cursor-theme', 'color-scheme')
EXTRA_FILES = ('.config/gtk-3.0/settings.ini', '.config/gtk-4.0/settings.ini', '.zshrc')
COPR_FILE = Path('/etc/yum.repos.d/_copr:copr.fedorainfracloud.org:sdegler:hyprland.repo')
UNIT = re.compile(r'[A-Za-z0-9_.@-]+\.service\Z')
PACKAGE = re.compile(r'[A-Za-z0-9][A-Za-z0-9+_.:-]*\Z')


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.new')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text())


def query(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def installed_packages(distro):
    command = ['pacman', '-Qq'] if distro == 'arch' else ['rpm', '-qa', '--qf', '%{NAME}.%{ARCH}\n']
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
    names = [name for name in result.stdout.splitlines() if name != 'gpg-pubkey.(none)']
    if not names or any(not PACKAGE.fullmatch(name) for name in names):
        raise ValueError('Не удалось получить полный список установленных пакетов.')
    return sorted(set(names))


def service_state(unit):
    if not UNIT.fullmatch(unit):
        raise ValueError('Некорректное имя службы')
    # is-enabled returns a nonzero status for disabled/not-found units, but still reports their state.
    try:
        result = subprocess.run(['systemctl', 'is-enabled', unit], capture_output=True, text=True, timeout=15)
        value = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return value if value in ('enabled', 'enabled-runtime', 'disabled', 'static', 'indirect',
                              'alias', 'masked', 'masked-runtime', 'not-found', 'linked', 'linked-runtime') else None


def system_state(extra_units=()):
    account = pwd.getpwuid(os.getuid())
    target = Path('/etc/systemd/system/display-manager.service')
    manager = Path(os.readlink(target)).name if target.is_symlink() else None
    units = list(dict.fromkeys((*SERVICES, *extra_units)))
    if manager and UNIT.fullmatch(manager) and manager not in units:
        units.append(manager)
    states = {}
    for unit in units:
        states[unit] = service_state(unit)
    settings = {}
    for key in SETTINGS:
        settings[key] = query(['gsettings', 'get', 'org.gnome.desktop.interface', key])
    return {'shell': account.pw_shell, 'user': account.pw_name, 'services': states,
            'default_target': query(['systemctl', 'get-default']), 'display_manager': manager,
            'settings': settings}


def before(record):
    path = record / 'before.json'
    if path.exists():
        return read_json(path)
    raw = record / 'raw'
    metadata = (raw / 'metadata').read_text().splitlines()
    if len(metadata) != 3 or metadata[0] not in ('arch', 'fedora'):
        raise ValueError('Повреждён журнал установки')
    distro, home, user = metadata
    services = {}
    for line in (raw / 'services').read_text().splitlines():
        unit, value = line.split('\t', 1)
        if UNIT.fullmatch(unit):
            services[unit] = value or None
    settings = {}
    for key in SETTINGS:
        value = (raw / ('gsettings-' + key)).read_text().strip()
        settings[key] = value or None
    files = {}
    for relative in EXTRA_FILES:
        files[relative] = (raw / 'home' / relative).exists() or (raw / 'home' / relative).is_symlink()
    value = {'schema': 1, 'distro': distro, 'home': home, 'user': user,
             'shell': (raw / 'shell').read_text().strip() or None,
             'services': services, 'settings': settings,
             'default_target': (raw / 'default-target').read_text().strip() or None,
             'display_manager': (raw / 'display-manager').read_text().strip() or None,
             'packages': (raw / 'packages-before').read_text().splitlines(),
             'files': files, 'oh_my_zsh_existed': (raw / 'oh-my-zsh-existed').read_text().strip() == 'true',
             'copr_existed': (raw / 'copr.repo').is_file(),
             'options': dict(line.split('\t', 1) for line in (raw / 'options').read_text().splitlines())}
    return value


def checkpoint(record, backup, phase):
    previous = before(record)
    write_json(record / 'before.json', previous)
    baseline = (record / 'raw/packages-baseline').read_text().splitlines()
    packages = installed_packages(previous['distro'])
    mode = record / 'raw/package-mode'
    new_packages = sorted(set(packages) - set(baseline))
    if mode.is_file() and mode.read_text() == 'upgrade':
        new_packages = []  # Never classify a failed OS upgrade as rice-owned packages.
    result = {'schema': 1, 'phase': phase, 'updated': now(), 'backup': str(backup.resolve()),
              'baseline_packages': sorted(set(baseline)), 'packages': packages,
              'new_packages': new_packages, 'system': system_state(previous['services']),
              'copr_sha256': hashlib.sha256(COPR_FILE.read_bytes()).hexdigest() if COPR_FILE.is_file() else None}
    write_json(record / 'after.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--phase', required=True)
    args = parser.parse_args()
    checkpoint(args.record, args.backup, args.phase)
