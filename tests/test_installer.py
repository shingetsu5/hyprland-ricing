import contextlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


configure = load('rice_configure', 'installer/configure.py')
updates = load('rice_updates', 'waybar/scripts/updates_run.py')
assets = load('rice_assets', 'installer/assets.py')
profiles = load('rice_profiles', 'hypr/power-profile.py')


def completed(code=0, out='', err=''):
    return subprocess.CompletedProcess([], code, out, err)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'repo'
        for name in configure.CONFIG_DIRS + ('wlogout', 'systemd'):
            shutil.copytree(ROOT / name, self.repo / name, ignore=configure.ignore_generated)
        (self.repo / 'Pictures/wallpapers').mkdir(parents=True)
        (self.repo / 'Pictures/wallpapers/moonlit-forest-4k.png').write_bytes(b'new wallpaper')
        (self.repo / 'Pictures/ascii_2.txt').write_text('ascii')
        self.home = self.base / 'user'
        (self.home / '.config/hypr').mkdir(parents=True)
        (self.home / '.config/hypr/hyprland.conf').write_text('env = XCURSOR_THEME,Existing\nenv = XCURSOR_SIZE,32\n')
        (self.home / '.bashrc').write_text('keep bashrc')

    def prepare(self, label='stage', battery=True, cursor=True, wallpapers=True):
        stage = self.base / label
        args = types.SimpleNamespace(root=self.repo, stage=stage, target_home=self.home,
                  battery=str(battery).lower(), cursor=str(cursor).lower(), wallpapers=str(wallpapers).lower(),
                  monitor=['eDP-1|3072x1920|165|2', 'DP-1|3840x2160|60|1.5'])
        with contextlib.redirect_stdout(io.StringIO()), patch.object(configure.shutil, 'which', return_value=None):
            configure.prepare(args)
        return stage

    def test_all_battery_cursor_wallpaper_combinations(self):
        for index, choices in enumerate(itertools.product((False, True), repeat=3)):
            battery, cursor, wallpapers = choices
            with self.subTest(choices=choices):
                stage = self.prepare(str(index), *choices)
                bar = (stage / '.config/waybar/config.jsonc').read_text()
                hypr = (stage / '.config/hypr/hyprland.conf').read_text()
                self.assertEqual('"battery",' in bar, battery)
                self.assertEqual('Bibata-Modern-Ice' in hypr, cursor)
                self.assertEqual('env = XCURSOR_THEME,Existing' in hypr, not cursor)
                self.assertEqual((stage / 'Pictures/wallpapers').exists(), wallpapers)
                self.assertIn('3072x1920@165, auto, 2', (stage / '.config/hypr/monitors.conf').read_text())
                self.assertIn('3840x2160@60, auto, 1.5', (stage / '.config/hypr/monitors.conf').read_text())
                self.assertEqual((self.home / '.bashrc').read_text(), 'keep bashrc')

    def test_preserve_existing_wallpaper_without_copy(self):
        image = self.home / 'Изображения/Мои обои/forest.png'
        image.parent.mkdir(parents=True); image.write_bytes(b'existing image')
        (self.home / '.config/hypr/current-wallpaper').write_text(str(image))
        stage = self.prepare(wallpapers=False)
        self.assertEqual((stage / '.config/hypr/current-wallpaper').read_text().strip(), str(image))
        preferences = json.loads((stage / '.config/appearance/preferences.json').read_text())
        self.assertEqual(preferences['wallpaper_dir'], str(image.parent))
        self.assertIn(str(image.parent), (stage / '.config/quickshell/WallpaperSettings.qml').read_text())
        self.assertFalse((stage / 'Pictures').exists())

    def test_deploy_backups_and_preserves_unrelated_files(self):
        stage = self.prepare()
        (self.home / 'Pictures/wallpapers').mkdir(parents=True)
        original_wallpaper = self.home / 'Pictures/wallpapers/moonlit-forest-4k.png'
        original_wallpaper.write_bytes(b'keep this image')
        units = self.home / '.config/systemd/user'; units.mkdir(parents=True)
        (units / 'unrelated.service').write_text('keep service')
        backup = self.base / 'backup'
        with contextlib.redirect_stdout(io.StringIO()):
            configure.deploy(types.SimpleNamespace(stage=stage, target_home=self.home, backup=backup))
        self.assertIn('Existing', (backup / '.config/hypr/hyprland.conf').read_text())
        self.assertEqual((self.home / '.bashrc').read_text(), 'keep bashrc')
        self.assertEqual((units / 'unrelated.service').read_text(), 'keep service')
        self.assertEqual(original_wallpaper.read_bytes(), b'keep this image')
        self.assertTrue((self.home / '.local/share/fastfetch/ascii_2.txt').is_file())

    def test_failed_deploy_restores_old_configuration(self):
        stage = self.prepare()
        original = (self.home / '.config/hypr/hyprland.conf').read_text()
        real_copytree = shutil.copytree
        def fail_once(source, destination, *args, **kwargs):
            if Path(source) == stage / '.config/kitty':
                raise OSError('simulated disk failure')
            return real_copytree(source, destination, *args, **kwargs)
        with patch.object(configure.shutil, 'copytree', side_effect=fail_once), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(OSError):
                configure.deploy(types.SimpleNamespace(stage=stage, target_home=self.home, backup=self.base / 'backup'))
        self.assertEqual((self.home / '.config/hypr/hyprland.conf').read_text(), original)
        self.assertFalse((self.home / '.config/waybar').exists())

    def test_only_offered_monitor_values_are_accepted(self):
        for bad in ['|1234x5678|60|1', '|3840x2160|59.94|1', '|3840x2160|60|1.25', '|preferred|144|1']:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                configure.monitor_rule(bad)
        self.assertEqual(configure.monitor_rule('|preferred|auto|1'), 'monitor = , preferred, auto, 1')


class RuntimeTests(unittest.TestCase):
    def test_arch_empty_aur_and_repository_failures(self):
        with patch.object(updates.shutil, 'which', return_value='/usr/bin/yay'), patch.object(updates.subprocess, 'run', side_effect=[completed(2), completed(1)]):
            self.assertEqual(updates.collect_arch_updates(), [])
        with patch.object(updates.subprocess, 'run', return_value=completed(1, err='network error')):
            with self.assertRaises(updates.UpdateError):
                updates.collect_arch_updates()

    def test_fedora_json_updates_and_failures(self):
        listing = {'updates': [{'name': 'kernel', 'arch': 'x86_64', 'evr': '1-2', 'repository': 'updates'}]}
        with patch.object(updates.subprocess, 'run', return_value=completed(100, json.dumps(listing))):
            self.assertEqual(updates.collect_fedora_updates(), [('DNF', 'kernel.x86_64 → 1-2')])
        for code, text in [(1, ''), (100, 'garbled'), (100, '{}')]:
            with patch.object(updates.subprocess, 'run', return_value=completed(code, text)):
                with self.assertRaises(updates.UpdateError):
                    updates.collect_fedora_updates()
        with patch.object(updates.subprocess, 'run', return_value=completed(0, '{}')):
            self.assertEqual(updates.collect_fedora_updates(), [])

    def test_upgrade_uses_the_right_manager_without_automatic_erasing(self):
        for distro, command in [('fedora', ['sudo', 'dnf5', '--best', '--setopt=skip_broken=False', 'upgrade']),
                                ('arch', ['yay', '-Syu'])]:
            with patch.object(updates, 'distro', return_value=distro), patch.object(updates.shutil, 'which', return_value='/usr/bin/yay'):
                self.assertEqual(updates.upgrade_command(), command)
        with patch.object(updates, 'distro', return_value='arch'), patch.object(updates.shutil, 'which', return_value=None):
            self.assertEqual(updates.upgrade_command(), ['sudo', 'pacman', '-Syu'])

    def test_profiles_support_legacy_provider_and_set_errors(self):
        with patch.object(profiles.subprocess, 'run', side_effect=[completed(1, err='unknown service'), completed(0, 's "balanced"\n')]) as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(profiles.control('get'), 0)
            self.assertIn('balanced', output.getvalue())
            self.assertIn('net.hadess.PowerProfiles', run.call_args.args[0])
        with patch.object(profiles.subprocess, 'run', side_effect=[completed(0, 's "balanced"\n'), completed(1, err='not supported')]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(profiles.control('set', 'performance'), 1)

    def test_theme_restore_does_not_override_preserved_cursor(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            theme = home / '.themes/Flat-Remix-GTK-Blue-Dark'; theme.mkdir(parents=True)
            appearance = home / '.config/appearance'; appearance.mkdir(parents=True)
            (appearance / 'preferences.json').write_text('{"replace_cursor":false}')
            gtk = home / '.config/gtk-3.0/settings.ini'; gtk.parent.mkdir()
            gtk.write_text('[Settings]\ngtk-cursor-theme-name=Existing\n')
            writes = []
            fake_settings = types.SimpleNamespace(get_string=lambda key: 'prefer-dark', delay=lambda: None,
                         apply=lambda: None, set_string=lambda key, value: writes.append((key, value)))
            fake_gio = types.SimpleNamespace(Settings=types.SimpleNamespace(new=lambda name: fake_settings, sync=lambda: None))
            repository = types.ModuleType('gi.repository'); repository.Gio = fake_gio; repository.GLib = object()
            with patch.dict(sys.modules, {'gi': types.ModuleType('gi'), 'gi.repository': repository}), patch.dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=temporary), patch.object(sys, 'argv', ['theme-switch.py', '--restore']), patch.object(subprocess, 'run', return_value=completed()), contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(ROOT / 'appearance/theme-switch.py'), run_name='__main__')
            self.assertNotIn('cursor-theme', [key for key, value in writes])
            self.assertIn('gtk-cursor-theme-name = Existing', gtk.read_text())

    def test_empty_wallpaper_directory_does_not_start_daemon(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / '.config/appearance').mkdir(parents=True)
            (home / '.config/appearance/preferences.json').write_text(json.dumps({'wallpaper_dir': str(home / 'empty')}))
            mockbin = home / 'bin'; mockbin.mkdir()
            daemon = mockbin / 'awww'; daemon.write_text('#!/bin/sh\nexit 99\n'); daemon.chmod(0o755)
            env = os.environ.copy(); env.update(HOME=temporary, PATH=str(mockbin) + ':' + env['PATH'])
            result = subprocess.run(['bash', str(ROOT / 'hypr/wallpaper.sh'), 'start'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('keeping the existing background', result.stderr)


class MenuAndAssetTests(unittest.TestCase):
    def test_both_previews_accept_presets_and_do_not_write_home(self):
        for distro in ('arch', 'fedora'):
            with self.subTest(distro=distro), tempfile.TemporaryDirectory() as home:
                command = 'set -Eeuo pipefail; RICE_ROOT=$1; source "$1/installer/common.sh"; rice_detect_monitors() { :; }; rice_main "$2" --dry-run'
                env = os.environ.copy(); env['HOME'] = home
                answers = '999\n2\n5\n6\n2\n2\n2\n2\n2\n2\n'
                result = subprocess.run(['bash', '-c', command, 'preview', str(ROOT), distro], input=answers, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('3840x2160, частота 165, масштаб 150%', result.stdout)
                for label in ('Батарея: нет', 'Обои из репозитория: нет', 'Курсор Bibata: нет'):
                    self.assertIn(label, result.stdout)
                self.assertIn('Выбери номер', result.stdout)
                self.assertEqual(list(Path(home).iterdir()), [])

    def test_unsupported_mode_is_rejected_before_installation(self):
        command = 'set -Eeuo pipefail; RICE_ROOT=$1; source "$1/installer/common.sh"; RICE_MONITOR_RULES=(); rice_monitor_options eDP-1 "3072x1920@165.00Hz"; printf "%s\\n" "${RICE_MONITOR_RULES[@]}"'
        result = subprocess.run(['bash', '-c', command, 'monitor', str(ROOT)], input='5\n6\n4\n6\n3\n', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('не сообщил о поддержке', result.stdout)
        self.assertIn('eDP-1|3072x1920|165|2', result.stdout)

    def test_installation_flow_with_mock_package_and_service_commands(self):
        # Exercise both full flows; only compiler and Hyprland's parser run for real.
        for distro in ('arch', 'fedora'):
            with self.subTest(distro=distro), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary); home = base / 'home'; home.mkdir()
                mockbin = base / 'bin'; mockbin.mkdir()
                log = base / 'calls.log'
                for command in ('sudo', 'yay', 'systemctl', 'fc-cache'):
                    path = mockbin / command
                    path.write_text('#!/bin/sh\nprintf "%s\\n" "' + command + ' $*" >> "$RICE_TEST_CALLS"\nexit 0\n')
                    path.chmod(0o755)
                for name, output in [('pacman', 'base-package'), ('rpm', 'base-package.x86_64')]:
                    path = mockbin / name
                    path.write_text('#!/bin/sh\nprintf "%s\\n" "' + output + '"\n')
                    path.chmod(0o755)
                fake_assets = base / 'fake-assets.py'
                fake_assets.write_text('import pathlib,sys\nout=pathlib.Path(sys.argv[sys.argv.index("--output")+1])\nfor kind,names in [(".themes",["Flat-Remix-GTK-Blue-Light","Flat-Remix-GTK-Blue-Dark"]),(".icons",["Flat-Remix-Blue-Light","Flat-Remix-Blue-Dark"])]:\n for name in names:\n  p=out/kind/name;p.mkdir(parents=True,exist_ok=True);(p/"index.theme").write_text("theme")\n')
                wrapper = mockbin / 'python3'
                wrapper.write_text('#!/bin/bash\nif [[ $1 == */installer/assets.py ]]; then shift; exec "$RICE_REAL_PYTHON" "$RICE_FAKE_ASSETS" "$@"; fi\nexec "$RICE_REAL_PYTHON" "$@"\n')
                wrapper.chmod(0o755)
                # Arch uses themes installed by AUR; the mock package commands do not create them.
                if distro == 'arch':
                    subprocess.run([sys.executable, str(fake_assets), '--output', str(home)], check=True)
                env = os.environ.copy()
                env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), XDG_STATE_HOME=str(home / '.local/state'),
                    PATH=str(mockbin) + ':' + env['PATH'], RICE_TEST_CALLS=str(log), RICE_REAL_PYTHON=sys.executable,
                    RICE_FAKE_ASSETS=str(fake_assets))
                command = 'set -Eeuo pipefail; RICE_ROOT=$1; source "$1/installer/common.sh"; rice_preflight() { :; }; rice_detect_monitors() { :; }; rice_main "$2"'
                answers = ['2', '1', '1', '2', '2', '2', '2']
                if distro == 'fedora': answers.append('1')  # explicit COPR consent
                answers.extend(['1', '2'])  # apply, do not reboot
                result = subprocess.run(['bash', '-c', command, 'install', str(ROOT), distro], input='\n'.join(answers) + '\n', env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('Установка завершена.', result.stdout)
                self.assertTrue((home / '.config/waybar/libclock-hover.so').is_file())
                self.assertFalse((home / 'Pictures').exists())
                calls = log.read_text()
                self.assertNotIn('enable sddm', calls)
                self.assertNotIn('reboot', calls)
                self.assertNotIn('bibata-cursor-theme', calls)
                if distro == 'arch':
                    self.assertIn('sudo pacman -Syu', calls)
                    self.assertIn('sudo pacman -S --needed', calls)
                    self.assertIn('yay -S --needed', calls)
                else:
                    self.assertIn('sudo dnf5 copr enable sdegler/hyprland', calls)
                    self.assertIn('--setopt=skip_unavailable=False --setopt=skip_broken=False install', calls)

    def test_zsh_choice_changes_login_shell_including_existing_oh_my_zsh(self):
        # Account operations are shell functions here; the real account is untouched.
        for installed, initial, selected, expect_change in [
            (False, '/bin/bash', True, True),
            (True, '/bin/bash', True, True),
            (True, '/bin/zsh', True, False),
            (False, '/bin/bash', False, False),
        ]:
            with self.subTest(installed=installed, initial=initial, selected=selected), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                if installed:
                    (home / '.oh-my-zsh').mkdir()
                (home / '.zshrc').write_text('keep zshrc')
                (home / '.bashrc').write_text('keep bashrc')
                env = os.environ.copy()
                env.update(HOME=temporary, MOCK_SHELL=initial, RICE_TEST_CALLS=str(home / 'calls'))
                script = r'''set -Eeuo pipefail
source "$1/installer/common.sh"
RICE_ZSH=$2
RICE_TEMP=$HOME
command() {
    case "$*" in
        '-v zsh') printf '/usr/bin/zsh\n' ;;
        '-v chsh') printf '/usr/bin/chsh\n' ;;
        *) builtin command "$@" ;;
    esac
}
getent() { printf '%s:x:1000:1000:Test:%s:%s\n' "$2" "$HOME" "$MOCK_SHELL"; }
readlink() { if [[ ${@: -1} == */zsh ]]; then printf '/usr/bin/zsh\n'; else printf '/usr/bin/bash\n'; fi; }
sudo() {
    [[ $1 == chsh && $2 == -s && $3 == /usr/bin/zsh && $4 == "$(id -un)" ]]
    printf '%s\n' "$*" >> "$RICE_TEST_CALLS"
    MOCK_SHELL=/usr/bin/zsh
}
curl() { printf '%s\n' '#!/bin/sh' 'mkdir -p "$HOME/.oh-my-zsh"' > "${@: -1}"; }
rice_install_zsh
'''
                result = subprocess.run(['bash', '-c', script, 'zsh-test', str(ROOT), str(selected).lower()], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((home / 'calls').exists(), expect_change)
                self.assertEqual((home / '.zshrc').read_text(), 'keep zshrc')
                self.assertEqual((home / '.bashrc').read_text(), 'keep bashrc')
                if selected:
                    self.assertIn('Zsh настроен как основная оболочка.', result.stdout)

    def test_zsh_shell_change_cannot_silently_succeed(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary); (home / '.oh-my-zsh').mkdir()
            env = os.environ.copy(); env['HOME'] = temporary
            script = r'''set -Eeuo pipefail
source "$1/installer/common.sh"
RICE_ZSH=true
command() { if [[ $2 == zsh ]]; then printf '/usr/bin/zsh\n'; else printf '/usr/bin/chsh\n'; fi; }
getent() { printf '%s:x:1000:1000:Test:%s:/bin/bash\n' "$2" "$HOME"; }
readlink() { printf '%s\n' "${@: -1}"; }
sudo() { return 0; }
rice_install_zsh
'''
            result = subprocess.run(['bash', '-c', script, 'zsh-test', str(ROOT)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Основная оболочка не изменилась.', result.stderr)
            self.assertNotIn('Zsh настроен как основная оболочка.', result.stdout)

    def test_asset_checksum_failure_stops_before_extracting(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'home'
            with patch.object(assets, 'fetch', side_effect=lambda url, path: path.write_bytes(b'wrong archive')), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    assets.install(output, False)
            self.assertEqual(list(output.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
