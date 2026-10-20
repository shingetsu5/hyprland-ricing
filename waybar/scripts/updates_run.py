#!/usr/bin/env python3
"""Inspect Arch/Fedora updates; preserve interactive package-manager error handling."""
import argparse
import fcntl
import html
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


class UpdateError(RuntimeError):
    pass


def collect_arch_updates():
    with tempfile.TemporaryDirectory(prefix='rice-checkupdates-') as database:
        env = os.environ.copy()
        env['CHECKUPDATES_DB'] = database
        env['LC_ALL'] = 'C'
        result = subprocess.run(['checkupdates'], env=env, capture_output=True, text=True)
    if result.returncode not in (0, 2):
        raise UpdateError(result.stderr.strip() or 'Could not check repository updates')
    updates = []
    for line in result.stdout.splitlines():
        if line.strip():
            updates.append(('pacman', line.strip()))
    if shutil.which('yay'):
        result = subprocess.run(['yay', '-Qua'], env=env, capture_output=True, text=True)
        # Like pacman -Qu, yay returns 1 with empty output when nothing is newer.
        no_updates = (result.returncode == 1 and not result.stdout.strip()
                      and not result.stderr.strip())
        if result.returncode and not no_updates:
            raise UpdateError(result.stderr.strip() or 'Could not check AUR updates')
        for line in result.stdout.splitlines():
            if line.strip():
                updates.append(('AUR', line.strip()))
    return updates


def distro():
    for line in Path('/etc/os-release').read_text().splitlines():
        if line.startswith('ID='):
            name = line[3:].strip().strip('"')
            if name in ('arch', 'fedora'):
                return name
    raise UpdateError('Unsupported distribution')


def collect_fedora_updates():
    env = os.environ.copy()
    env['LC_ALL'] = 'C'
    result = subprocess.run(['dnf5', '--quiet', '--color=never', 'check-upgrade', '--json'],
                            env=env, capture_output=True, text=True)
    if result.returncode not in (0, 100):
        raise UpdateError(result.stderr.strip() or 'Could not check Fedora updates')
    if not result.stdout.strip():
        if result.returncode == 0:
            return []
        raise UpdateError('DNF reported updates without a package list')
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise UpdateError('Invalid DNF update list') from error
    if not isinstance(data, dict):
        raise UpdateError('Unexpected DNF update list')
    updates = []
    seen = set()
    for section in data.values():
        if not isinstance(section, list):
            continue
        for package in section:
            if not isinstance(package, dict) or not all(key in package for key in ('name', 'arch', 'evr')):
                continue
            key = (package['name'], package['arch'])
            if key not in seen:
                seen.add(key)
                updates.append(('DNF', f"{package['name']}.{package['arch']} → {package['evr']}"))
    if result.returncode == 100 and not updates:
        raise UpdateError('DNF reported updates, but their format is unsupported')
    return updates


def collect_updates():
    return collect_fedora_updates() if distro() == 'fedora' else collect_arch_updates()


def upgrade_command():
    if distro() == 'fedora':
        return ['sudo', 'dnf5', '--best', '--setopt=skip_broken=False', 'upgrade']
    return ['yay', '-Syu'] if shutil.which('yay') else ['sudo', 'pacman', '-Syu']


def menu():
    updates = collect_updates()
    if not updates:
        subprocess.run(['notify-send', 'Обновлений нет'], check=False)
        return 0
    if distro() == 'fedora':
        action = 'Обновить всю систему (DNF)'
    else:
        action = 'Обновить всю систему (pacman + AUR)' if shutil.which('yay') else 'Обновить всю систему (pacman)'
    rows = [action] + [f'[{source}] {line}' for source, line in updates]
    message = 'Выбери пакет для просмотра или обнови всю систему.'
    while True:
        result = subprocess.run(
            ['rofi', '-dmenu', '-i', '-no-custom', '-p', 'Updates', '-mesg', message,
             '-theme', str(Path.home() / '.config/rofi/config.rasi')],
            input='\n'.join(rows) + '\n', capture_output=True, text=True,
        )
        if result.returncode:
            return 0
        choice = result.stdout.strip()
        if choice == action:
            return subprocess.run(
                ['kitty', '-e', sys.executable, str(Path(__file__).resolve()), '--upgrade'],
                check=False,
            ).returncode
        if choice in rows:
            message = html.escape(choice) + '\nДля установки требуется полное обновление системы.'
        else:
            return 0


def upgrade():
    # Let pacman/yay resolve conflicts interactively. Never skip dependencies,
    # auto-remove packages or offer partial upgrades as a conflict workaround.
    command = upgrade_command()
    print('Обновление системы', flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode:
        print('\nОбновление не завершено. Причина указана выше.', flush=True)
    else:
        print('\nОбновление завершено.', flush=True)
    if sys.stdin.isatty():
        try:
            input('Нажми Enter, чтобы закрыть окно…')
        except EOFError:
            pass
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--count', action='store_true')
    mode.add_argument('--menu', action='store_true')
    mode.add_argument('--upgrade', action='store_true')
    args = parser.parse_args()
    if args.count:
        updates = collect_updates()
        print(f'󰏗  {len(updates)}' if updates else '')
        return 0
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()))
    with (runtime / f'arch-rice-updates-{"upgrade" if args.upgrade else "menu"}-{os.getuid()}.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return upgrade() if args.upgrade else menu()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (UpdateError, OSError) as error:
        print(f'Updates: {error}', file=sys.stderr)
        if '--count' in sys.argv:
            print('󰏗  !')
        elif '--menu' in sys.argv and shutil.which('notify-send'):
            subprocess.run(['notify-send', 'Ошибка проверки обновлений', str(error)], check=False)
        sys.exit(1)
