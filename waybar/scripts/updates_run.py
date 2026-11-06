#!/usr/bin/env python3
"""Inspect Arch/Fedora updates; preserve interactive package-manager error handling."""
import argparse
import fcntl
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
import re
import time


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
                            env=env, capture_output=True, text=True, timeout=150)
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


def window_path():
    return Path(__file__).resolve().parents[2] / 'quickshell/updates'


def gui_environment():
    env = os.environ.copy()
    env.pop('GTK_THEME', None)
    env['QT_QPA_PLATFORM'] = 'wayland'
    env['QT_QPA_PLATFORMTHEME'] = 'xdgdesktopportal'
    return env


def menu():
    path = str(window_path())
    if subprocess.run(['quickshell', 'ipc', '-p', path, 'call', 'updates', 'reveal'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        return 0
    return subprocess.run(['quickshell', '-p', path, '--no-duplicate'],
                          env=gui_environment(), check=False).returncode


def request_dialog(options, message):
    # A separate instance keeps terminal error handling independent of the updates window.
    with tempfile.TemporaryDirectory(prefix='rice-update-dialog-') as directory:
        request = Path(directory) / 'request.json'
        request.write_text(json.dumps({'message': message, 'options': options}, ensure_ascii=False))
        env = gui_environment()
        env['RICE_UPDATE_DIALOG'] = str(request)
        result = subprocess.run(['quickshell', '-p', str(window_path())], env=env, check=False)
        reply = request.with_name('reply.json')
        if result.returncode or not reply.is_file():
            return options[0]
        index = json.loads(reply.read_text())['index']
        return options[index] if isinstance(index, int) and 0 <= index < len(options) else options[0]


def dialog_data(path):
    data = json.loads(path.read_text())
    if not isinstance(data.get('message'), str) or not isinstance(data.get('options'), list):
        raise UpdateError('Invalid update dialog')
    if not data['options'] or any(not isinstance(value, str) for value in data['options']):
        raise UpdateError('Invalid dialog options')
    return data


def launch_upgrade():
    if not shutil.which('kitty'):
        raise UpdateError('Не найден терминал Kitty')
    # Detached terminal survives closing the Quickshell window. Upgrade has its own lock.
    subprocess.Popen(['kitty', '--title', 'Обновление системы', '-e', sys.executable,
                      str(Path(__file__).resolve()), '--upgrade'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return 0


def package_details():
    name = distro()
    updates = collect_updates()
    installed = {}
    if name == 'fedora':
        result = subprocess.run(['rpm', '-qa', '--qf', '%{NAME}.%{ARCH}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\n'],
                                capture_output=True, text=True, check=True, timeout=30)
        for line in result.stdout.splitlines():
            if '\t' in line:
                package, version = line.split('\t', 1)
                installed[package] = version.removeprefix('0:')
    packages = []
    for source, line in updates:
        if name == 'fedora':
            package, available = line.split(' → ', 1)
            current = installed.get(package, '—')
        else:
            match = re.fullmatch(r'(\S+)\s+(\S+)\s+->\s+(\S+)', line)
            if not match:
                raise UpdateError('Не удалось прочитать версии пакета: ' + line)
            package, current, available = match.groups()
        packages.append({'name': package, 'current': current, 'available': available,
                         'source': 'AUR' if source == 'AUR' else 'Система'})
    return {'distro': 'Fedora' if name == 'fedora' else 'Arch Linux',
            'manager': 'DNF5' if name == 'fedora' else 'pacman / AUR' if shutil.which('yay') else 'pacman',
            'packages': packages, 'checked_at': datetime.now().strftime('%H:%M')}


CACHE_TTL = 600


def cache_directory():
    return Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'rice-updates'


def read_cache():
    try:
        data = json.loads((cache_directory() / 'packages.json').read_text())
        if not isinstance(data, dict) or not isinstance(data.get('attempted_at'), (int, float)):
            return {}
        if 'packages' in data and not isinstance(data['packages'], list):
            return {}
        return data
    except (OSError, ValueError):
        return {}


def write_cache(data):
    directory = cache_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(directory / 'packages.json')
    finally:
        temporary.unlink(missing_ok=True)


def cache_worker_running():
    directory = cache_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'refresh.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def start_cache_refresh(force=False):
    command = [sys.executable, str(Path(__file__).resolve()), '--refresh-cache']
    if force:
        command.append('--force')
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def refresh_cache(force=False):
    directory = cache_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'refresh.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if force else fcntl.LOCK_NB))
        except BlockingIOError:
            return 0
        previous = read_cache()
        if not force and 0 <= time.time() - previous.get('attempted_at', 0) < CACHE_TTL:
            return 0
        attempted_at = time.time()
        try:
            data = package_details()
            data['checked_at'] = datetime.now().strftime('%d.%m %H:%M')
        except (UpdateError, OSError, subprocess.SubprocessError, ValueError) as error:
            data = previous.copy()
            data['error'] = str(error)
        data['attempted_at'] = attempted_at
        write_cache(data)
        return 1 if data.get('error') else 0


def cached_details(force=False):
    data = read_cache()
    running = cache_worker_running()
    age = time.time() - data.get('attempted_at', 0)
    if (force or not data or age < 0 or age >= CACHE_TTL) and not running:
        start_cache_refresh(force)
        running = True
    result = data.copy()
    result['refreshing'] = running
    result['pending'] = 'packages' not in data and not data.get('error')
    return result


def upgrade():
    # Let pacman/yay resolve conflicts interactively. Never skip dependencies,
    # auto-remove packages or offer partial upgrades as a conflict workaround.
    print('Обновление системы', flush=True)
    if distro() == 'fedora':
        from updates_fedora import main as fedora_upgrade
        code = fedora_upgrade()
    else:
        code = subprocess.run(upgrade_command(), check=False).returncode
    if code:
        print('\nОбновление не завершено. Причина указана выше.', flush=True)
    else:
        # Discard the pre-install list, then rebuild it outside the terminal.
        (cache_directory() / 'packages.json').unlink(missing_ok=True)
        start_cache_refresh(force=True)
        print('\nОбновление завершено.', flush=True)
    if sys.stdin.isatty():
        try:
            input('Нажми Enter, чтобы закрыть окно…')
        except EOFError:
            pass
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--count', action='store_true')
    mode.add_argument('--menu', action='store_true')
    mode.add_argument('--upgrade', action='store_true')
    mode.add_argument('--json', action='store_true')
    mode.add_argument('--refresh-cache', action='store_true')
    parser.add_argument('--force', action='store_true')
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--dialog-read', type=Path)
    mode.add_argument('--dialog-answer', type=Path)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    if args.refresh_cache:
        return refresh_cache(args.force)
    if args.json:
        try:
            print(json.dumps(cached_details(args.force), ensure_ascii=False))
            return 0
        except (UpdateError, OSError, subprocess.SubprocessError, ValueError) as error:
            print(json.dumps({'error': str(error)}, ensure_ascii=False))
            return 1
    if args.dialog_read:
        print(json.dumps(dialog_data(args.dialog_read), ensure_ascii=False))
        return 0
    if args.dialog_answer:
        data = dialog_data(args.dialog_answer)
        if args.index is None or not 0 <= args.index < len(data['options']):
            raise UpdateError('Некорректный ответ диалога')
        args.dialog_answer.with_name('reply.json').write_text(json.dumps({'index': args.index}))
        return 0
    if args.launch:
        return launch_upgrade()
    if args.count:
        # Waybar calls this every ten minutes; keep its existing text while checking.
        refresh_cache()
        data = cached_details()
        if data.get('error'):
            print('󰏗  !')
        elif 'packages' not in data:
            print('󰏗  …')
        else:
            count = len(data['packages'])
            print(f'󰏗  {count}' if count else '')
        return 0
    if args.menu:
        return menu()
    runtime = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'arch-rice-updates'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (runtime / 'upgrade.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Обновление уже запущено.', flush=True)
            return 1
        return upgrade()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (UpdateError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f'Updates: {error}', file=sys.stderr)
        if '--count' in sys.argv:
            print('󰏗  !')
        elif '--menu' in sys.argv and shutil.which('notify-send'):
            subprocess.run(['notify-send', 'Ошибка проверки обновлений', str(error)], check=False)
        sys.exit(1)
