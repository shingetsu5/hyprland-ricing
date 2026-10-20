#!/usr/bin/env python3
"""Restore rice backups; keep displaced user files in a separate archive."""
import argparse
import hashlib
from datetime import datetime
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys

import state

MANAGED = {'.config/' + name for name in
           ('hypr', 'waybar', 'kitty', 'rofi', 'swaync', 'quickshell', 'fastfetch', 'appearance', 'wlogout')}
MANAGED.update(('.config/systemd/user/quickshell-desktop-session.target',
                '.local/share/fonts/rice-nerd-symbols'))
MANAGED.update('.themes/' + name for name in ('Flat-Remix-GTK-Blue-Light', 'Flat-Remix-GTK-Blue-Dark'))
MANAGED.update('.icons/' + name for name in ('Flat-Remix-Blue-Light', 'Flat-Remix-Blue-Dark', 'Bibata-Modern-Ice'))
EXTRA = set(state.EXTRA_FILES) | {'.oh-my-zsh'}


def exists(path):
    return path.exists() or path.is_symlink()


def safe(root, relative):
    part = Path(relative)
    if not relative or part.is_absolute() or '..' in part.parts or str(part) != relative:
        raise ValueError('Недопустимый путь в журнале: ' + relative)
    path = root / part
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('Родительский каталог заменён символьной ссылкой: ' + str(parent))
    # A final symlink is archived as a link. Parent symlinks may not redirect writes.
    if root.resolve() not in (path.parent.resolve(), *path.parent.resolve().parents):
        raise ValueError('Путь выходит за пределы каталога: ' + relative)
    return path


def allowed(relative):
    return relative in MANAGED or relative in EXTRA or any(
        relative.startswith(prefix) for prefix in ('Pictures/wallpapers/', '.local/share/fastfetch/'))


def discover(home, directory):
    result = []
    associated = set()
    installations = directory / 'installations'
    if installations.exists():
        for record in sorted(installations.iterdir()):
            if not record.is_dir():
                continue
            after_path = record / 'after.json'
            if not after_path.is_file():
                continue  # An interrupted raw-only capture does not establish ownership.
            previous, after = state.before(record), state.read_json(after_path)
            if Path(previous['home']).resolve() != home.resolve():
                continue
            backup = Path(after['backup'])
            if backup.parent.resolve() != (directory / 'backups').resolve():
                raise ValueError('Резервная копия вне каталога backups')
            associated.add(backup.resolve())
            if not (record / 'uninstalled.json').exists():
                result.append({'id': record.name, 'record': record, 'backup': backup,
                               'before': previous, 'after': after, 'legacy': False})
    backups = directory / 'backups'
    if backups.exists():
        for backup in sorted(backups.iterdir()):
            if (backup.resolve() not in associated and (backup / 'installation.json').is_file()
                    and not (backup / 'uninstalled.json').exists()):
                result.append({'id': backup.name, 'record': backup, 'backup': backup, 'legacy': True})
    return sorted(result, key=lambda item: item['id'])


def file_plan(home, selected):
    actions = {}
    warnings = []
    for item in reversed(selected):
        backup = item['backup']
        manifest = backup / 'deployment.json'
        if manifest.is_file():
            data = state.read_json(manifest)
            for entry in data['managed']:
                relative = entry['path']
                if relative not in MANAGED or type(entry['had_original']) is not bool:
                    raise ValueError('Недопустимый объект в deployment.json')
                source = safe(backup, relative) if entry['had_original'] else None
                if source is not None and not exists(source):
                    raise ValueError('Отсутствует исходная резервная копия: ' + str(source))
                actions[relative] = source
            added = [entry['path'] for entry in data['added']]
        elif item['legacy']:
            warnings.append(item['id'] + ': старый формат; пакеты, оболочка и службы неизвестны.')
            for relative in sorted(MANAGED):
                source = safe(backup, relative)
                if exists(source):
                    actions[relative] = source
            added_path = backup / 'added-files.json'
            added = state.read_json(added_path) if added_path.is_file() else []
        else:
            # configure.deploy rolls back on failure; no manifest means no committed deployment.
            added = []
        for relative in added:
            if not any(relative.startswith(prefix) for prefix in ('Pictures/wallpapers/', '.local/share/fastfetch/')):
                raise ValueError('Недопустимый путь добавленного файла')
            actions[relative] = None
        if not item['legacy'] and manifest.is_file():
            previous = item['before']
            for relative, had_original in previous['files'].items():
                if relative not in state.EXTRA_FILES:
                    raise ValueError('Недопустимый файл настроек')
                # Existing .zshrc is deliberately preserved by the installer.
                if relative == '.zshrc' and had_original:
                    continue
                if relative == '.zshrc' and previous['options'].get('zsh') != 'true':
                    continue
                source = safe(item['record'] / 'raw/home', relative) if had_original else None
                if source is not None and not exists(source):
                    raise ValueError('Отсутствует резервная копия ' + relative)
                actions[relative] = source
            if not previous['oh_my_zsh_existed'] and previous['options'].get('zsh') == 'true':
                actions['.oh-my-zsh'] = None
    # Never accept overlapping owned objects from a malformed receipt.
    paths = [Path(relative) for relative in actions]
    if any(left in right.parents for left in paths for right in paths if left != right):
        raise ValueError('Перекрывающиеся пути в журнале установки')
    for relative in actions:
        if not allowed(relative):
            raise ValueError('Неизвестный объект удаления: ' + relative)
        safe(home, relative)
    return actions, warnings


def erase(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif exists(path):
        path.unlink()


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        target.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target)


def restore_files(home, archive, actions):
    completed = []
    try:
        for relative, source in actions.items():
            target = safe(home, relative)
            saved = safe(archive / 'home', relative)
            had_current = exists(target)
            if had_current:
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(saved))
            completed.append((target, saved, had_current))
            if source is not None:
                copy(source, target)
    except BaseException:
        for target, saved, had_current in reversed(completed):
            erase(target)
            if had_current:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(saved), str(target))
        raise


def package_candidates(selected, current):
    new, protected = set(), set()
    distros = set()
    for item in selected:
        if item['legacy']:
            return [], None
        previous, after = item['before'], item['after']
        distros.add(previous['distro'])
        baseline = set(after['baseline_packages'])
        if not protected:
            protected.update(previous['packages'])
        protected.update(baseline - set(previous['packages']))  # additions from full Arch upgrade
        new.update(after['new_packages'])
    if len(distros) != 1:
        raise ValueError('Журналы относятся к разным дистрибутивам')
    candidates = (new & set(current)) - protected
    if any(not state.PACKAGE.fullmatch(name) for name in candidates):
        raise ValueError('Некорректные имена пакетов в журнале')
    distro = next(iter(distros))
    if distro == 'fedora':
        # Protect all architectures of any name also owned outside this rice.
        outside = {name.rsplit('.', 1)[0] for name in set(current) - candidates}
        candidates = {name for name in candidates if name.rsplit('.', 1)[0] not in outside}
    return sorted(candidates), distro


def run(command):
    subprocess.run(command, check=True)


def remove_packages(distro, candidates, current):
    if not candidates:
        return
    if set(state.installed_packages(distro)) != set(current):
        raise ValueError('Список пакетов изменился. Запусти удаление ещё раз.')
    # Keep the actual account shell usable, including an externally selected shell.
    shell = pwd.getpwuid(os.getuid()).pw_shell
    if distro == 'arch':
        owner = state.query(['pacman', '-Qqo', shell])
    else:
        owner = state.query(['rpm', '-qf', '--qf', '%{NAME}.%{ARCH}', shell])
    if owner is None or owner in candidates:
        raise ValueError('Удаление затронет текущую оболочку или её пакет не удалось определить.')
    manager = Path('/etc/systemd/system/display-manager.service')
    if manager.is_symlink():
        unit_path = str(manager.resolve())
        query = ['pacman', '-Qqo', unit_path] if distro == 'arch' else ['rpm', '-qf', '--qf', '%{NAME}.%{ARCH}', unit_path]
        manager_owner = state.query(query)
        if manager_owner is None or manager_owner in candidates:
            raise ValueError('Удаление затронет сохранённый экран входа или его пакет не удалось определить.')
    if distro == 'arch':
        # No recursive/cascade flags: pacman rejects dependencies outside this exact set.
        run(['sudo', 'pacman', '-R', '--', *candidates])
    else:
        # RPM checks the exact set; DNF additionally protects all other package names.
        run(['sudo', 'rpm', '-e', '--test', '--', *candidates])
        protected = sorted({name.rsplit('.', 1)[0] for name in set(current) - set(candidates)})
        # protected_packages is an append-list in DNF5; preserve distro defaults too.
        run(['sudo', 'dnf5', '--setopt=protected_packages=' + ','.join(protected),
             '--setopt=skip_broken=False', 'remove', '--no-autoremove', '--', *candidates])


def system_plan(selected, current):
    desired = {}
    expected = {}
    for item in reversed(selected):
        if item['legacy']:
            continue
        previous, after = item['before'], item['after']['system']
        pairs = [('shell', previous.get('shell'), after.get('shell')),
                 ('default_target', previous.get('default_target'), after.get('default_target'))]
        pairs.extend(('service:' + key, value, after.get('services', {}).get(key))
                     for key, value in previous['services'].items())
        pairs.extend(('setting:' + key, value, after.get('settings', {}).get(key))
                     for key, value in previous['settings'].items())
        for key, old, new in pairs:
            if old is not None and new is not None and old != new:
                desired[key] = old
                expected.setdefault(key, new)
    # The launcher changes these values after installation, when a Hyprland session starts.
    runtime_values = {
        'gtk-theme': ("'Flat-Remix-GTK-Blue-Light'", "'Flat-Remix-GTK-Blue-Dark'"),
        'icon-theme': ("'Flat-Remix-Blue-Light'", "'Flat-Remix-Blue-Dark'"),
        'color-scheme': ("'prefer-light'", "'prefer-dark'"),
        'cursor-theme': ("'Bibata-Modern-Ice'",),
    }
    for item in reversed(selected):
        manifest = item['backup'] / 'deployment.json'
        if item['legacy'] or not manifest.is_file():
            continue
        choices = state.read_json(item['backup'] / 'installation.json') if (item['backup'] / 'installation.json').is_file() else {}
        for key, values in runtime_values.items():
            if key == 'cursor-theme' and not choices.get('cursor', False):
                continue
            old = item['before']['settings'].get(key)
            actual = current['settings'].get(key)
            if old is not None and actual in values and actual != old:
                desired['setting:' + key] = old
                expected['setting:' + key] = actual
    actions, warnings = {}, []
    for key, value in desired.items():
        if key.startswith('service:'):
            actual = current['services'].get(key.split(':', 1)[1])
        elif key.startswith('setting:'):
            actual = current['settings'].get(key.split(':', 1)[1])
        else:
            actual = current.get(key)
        if actual == value:
            continue
        if actual != expected[key]:
            warnings.append('Сохранено последующее изменение: ' + key)
        else:
            actions[key] = value
    managers = set()
    expected_manager = None
    original_manager = None
    for item in selected:
        if item['legacy']:
            continue
        old_manager = item['before'].get('display_manager')
        if original_manager is None and old_manager:
            original_manager = old_manager
        expected_manager = item['after']['system'].get('display_manager')
        managers.update(unit for unit in (old_manager, expected_manager) if unit)
    if expected_manager and current.get('display_manager') != expected_manager:
        warnings.append('Экран входа изменён после установки; его настройки сохранены.')
        for unit in managers:
            actions.pop('service:' + unit, None)
    elif original_manager and current['services'].get(original_manager) in (None, 'not-found'):
        warnings.append('Прежний экран входа недоступен; текущий сохранён.')
        for unit in managers:
            actions.pop('service:' + unit, None)
    return actions, warnings


def validate_system(actions):
    if 'shell' in actions:
        value = actions['shell']
        if not value.startswith('/') or not Path(value).is_file() or value not in Path('/etc/shells').read_text().splitlines():
            raise ValueError('Предыдущая оболочка недоступна: ' + value)
    for key, value in actions.items():
        if key.startswith('service:') and value not in ('enabled', 'disabled', 'not-found', 'enabled-runtime'):
            raise ValueError('Невозможно автоматически восстановить состояние службы: ' + key + ': ' + value)


def restore_system(actions):
    # Disable rice's manager before re-enabling the former one. Never stop running services.
    ordered = sorted(actions, key=lambda key: 0 if key.startswith('service:') and actions[key] in ('disabled', 'not-found') else 1)
    for key in ordered:
        value = actions[key]
        if key == 'shell':
            if not value.startswith('/') or not Path(value).is_file() or value not in Path('/etc/shells').read_text().splitlines():
                raise ValueError('Предыдущая оболочка недоступна: ' + value)
            run(['sudo', 'chsh', '-s', value, pwd.getpwuid(os.getuid()).pw_name])
            if pwd.getpwuid(os.getuid()).pw_shell != value:
                raise ValueError('Не удалось восстановить основную оболочку')
        elif key == 'default_target':
            if not re.fullmatch(r'[A-Za-z0-9_.@-]+\.target', value):
                raise ValueError('Некорректная цель systemd')
            run(['sudo', 'systemctl', 'set-default', value])
        elif key.startswith('service:'):
            unit = key.split(':', 1)[1]
            if not state.UNIT.fullmatch(unit):
                raise ValueError('Некорректная служба')
            if value in ('enabled', 'disabled', 'not-found', 'enabled-runtime'):
                command = 'enable' if value.startswith('enabled') else 'disable'
                args = ['sudo', 'systemctl', command]
                if value == 'enabled-runtime':
                    args.append('--runtime')
                run([*args, unit])
            else:
                raise ValueError('Неподдерживаемое прежнее состояние службы: ' + unit + ': ' + value)
        elif key.startswith('setting:'):
            name = key.split(':', 1)[1]
            if name not in state.SETTINGS:
                raise ValueError('Неизвестная настройка GTK')
            command = ['gsettings', 'set', 'org.gnome.desktop.interface', name, value]
            if not os.environ.get('DBUS_SESSION_BUS_ADDRESS') and shutil.which('dbus-run-session'):
                command = ['dbus-run-session', '--', *command]
            run(command)


def ensure_logged_out():
    active = bool(os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY') or os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'))
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            try:
                if path.stat().st_uid == os.getuid() and (path / 'comm').read_text().strip().lower() == 'hyprland':
                    active = True
            except (OSError, ProcessLookupError):
                pass
    if active:
        raise ValueError('Выйди из графической сессии и запусти удаление из TTY (Ctrl+Alt+F3). --dry-run доступен в терминале.')


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--from-id')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--packages', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    home = Path.home().resolve()
    directory = Path(os.environ.get('XDG_STATE_HOME', home / '.local/state')) / 'arch-hyprland-ricing'
    records = discover(home, directory)
    if args.list:
        for item in records:
            print(item['id'] + (' · старая установка' if item['legacy'] else ' · ' + item['before']['distro']))
        return
    if not records:
        print('Установка rice с журналом или резервной копией не найдена. Изменений нет.')
        return
    ids = [item['id'] for item in records]
    if args.from_id and args.from_id not in ids:
        raise ValueError('Установка не найдена')
    selected = records[ids.index(args.from_id):] if args.from_id else records
    actions, warnings = file_plan(home, selected)
    units = set()
    for item in selected:
        if not item['legacy']:
            units.update(item['before']['services'])
    current_system = state.system_state(units)
    systems, system_warnings = system_plan(selected, current_system)
    warnings.extend(system_warnings)
    tracked = not any(item['legacy'] for item in selected)
    current_packages = state.installed_packages(selected[0]['before']['distro']) if tracked else []
    candidates, distro = package_candidates(selected, current_packages) if tracked else ([], None)
    print('Будут отменены установки: ' + ', '.join(item['id'] for item in selected))
    for relative, source in sorted(actions.items()):
        print(('Восстановить: ' if source else 'Убрать в архив: ') + relative)
    for key, value in systems.items():
        print('Восстановить ' + key + ': ' + value)
    for message in warnings:
        print('Внимание: ' + message)
    if args.packages:
        print('Пакеты для удаления: ' + (', '.join(candidates) or 'нет подтверждённых пакетов'))
    else:
        print('Пакеты будут сохранены.')
    if tracked and any(item['before']['options'].get('copr') == 'true' for item in selected):
        print('COPR: вернуть прежний файл или убрать добавленный, если он не изменён после установки.')
    print('Репозиторий, журналы и исходные резервные копии сохраняются.')
    if args.dry_run or not args.apply:
        return
    if os.getuid() == 0:
        raise ValueError('Запусти скрипт от обычного пользователя, без sudo.')
    ensure_logged_out()
    validate_system(systems)
    # Root operations start only after the user has reviewed and confirmed the plan.
    run(['sudo', '-v'])
    progress = [item['record'] / 'uninstall-progress.json' for item in selected]
    existing = [state.read_json(path) for path in progress if path.is_file()]
    if existing:
        archives = {value['archive'] for value in existing}
        if len(archives) != 1:
            raise ValueError('Журналы незавершённого удаления не совпадают')
        archive = Path(next(iter(archives)))
        if archive.parent.resolve() != (directory / 'removed').resolve():
            raise ValueError('Некорректный архив незавершённого удаления')
        saved_plan = state.read_json(archive / 'plan.json')
        if saved_plan['installations'] != [item['id'] for item in selected]:
            raise ValueError('Для продолжения выбери ту же исходную установку')
        print('Продолжение удаления. Файлы уже восстановлены: ' + str(archive))
    else:
        archive = directory / 'removed' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
        archive.mkdir(parents=True, mode=0o700)
        print('Архив текущих файлов: ' + str(archive), flush=True)
        state.write_json(archive / 'system-before.json', current_system)
        state.write_json(archive / 'plan.json', {'files': list(actions), 'systems': systems,
                         'installations': [item['id'] for item in selected], 'packages': candidates if args.packages else []})
        restore_files(home, archive, actions)
    for item in selected:
        state.write_json(item['record'] / 'uninstall-progress.json', {'archive': str(archive), 'files_restored': True})
    restore_system(systems)
    # daemon-reload only: stopping this target would propagate to graphical-session.target.
    run(['systemctl', '--user', 'daemon-reload'])
    if shutil.which('fc-cache'):
        run(['fc-cache', '-f'])
    # Restore only a repository file whose content still matches the installer receipt.
    if tracked:
        first = selected[0]['before']
        latest = selected[-1]['after'].get('copr_sha256')
        current_hash = hashlib.sha256(state.COPR_FILE.read_bytes()).hexdigest() if state.COPR_FILE.is_file() else None
        if latest and current_hash == latest and any(item['before']['options'].get('copr') == 'true' for item in selected):
            saved = selected[0]['record'] / 'raw/copr.repo'
            if not (archive / 'copr.repo').exists():
                shutil.copy2(state.COPR_FILE, archive / 'copr.repo')
            if first['copr_existed']:
                if not saved.is_file():
                    raise ValueError('Отсутствует резервная копия COPR')
                run(['sudo', 'cp', '--', str(saved), str(state.COPR_FILE)])
            else:
                run(['sudo', 'rm', '--', str(state.COPR_FILE)])
        elif current_hash and latest and current_hash != latest:
            print('Внимание: файл COPR изменён после установки и сохранён.')
    if args.packages:
        remove_packages(distro, candidates, current_packages)
    for item in selected:
        state.write_json(item['record'] / 'uninstalled.json', {'time': state.now(), 'archive': str(archive),
                         'packages_removed': args.packages})
        (item['record'] / 'uninstall-progress.json').unlink(missing_ok=True)
    print('Удаление завершено. Текущие файлы сохранены: ' + str(archive))
    if not tracked:
        print('Старая установка: удалены только подтверждённые файлы. Неизвестные изменения требуют ручной проверки.')


if __name__ == '__main__':
    try:
        cli()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('Удаление остановлено: ' + str(error), file=sys.stderr)
        sys.exit(1)
