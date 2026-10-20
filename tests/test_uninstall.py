"""Removal tests use temporary homes; native system operations are always mocked."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'installer'))
import state
spec = importlib.util.spec_from_file_location('rice_uninstall', ROOT / 'installer/uninstall.py')
uninstall = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uninstall)


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.directory = self.home / '.local/state/arch-hyprland-ricing'
        self.current = {'shell': '/bin/bash', 'services': {}, 'settings': {}, 'default_target': 'graphical.target'}

    def put(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def record(self, label='001', original=True):
        record = self.directory / 'installations' / label
        backup = self.directory / 'backups' / label
        previous = {'schema': 1, 'distro': 'arch', 'home': str(self.home), 'user': 'test',
                    'packages': ['base'], 'files': {}, 'oh_my_zsh_existed': True,
                    'copr_existed': False, 'options': {}, 'services': {}, 'settings': {},
                    'shell': '/bin/bash', 'default_target': 'graphical.target'}
        after = {'backup': str(backup), 'baseline_packages': ['base', 'os-upgrade-dep'],
                 'new_packages': ['hyprland', 'rice-dep'], 'system': self.current.copy()}
        state.write_json(record / 'before.json', previous)
        state.write_json(record / 'after.json', after)
        state.write_json(backup / 'deployment.json', {'managed': [
            {'path': '.config/hypr', 'had_original': original},
            {'path': '.config/waybar', 'had_original': False}],
            'added': [{'path': 'Pictures/wallpapers/rice.png'}]})
        if original:
            self.put(backup / '.config/hypr/hyprland.conf', 'old ' + label)
        self.put(self.home / '.config/hypr/hyprland.conf', 'edited rice')
        self.put(self.home / '.config/waybar/config', 'rice bar')
        self.put(self.home / 'Pictures/wallpapers/rice.png', 'edited wallpaper')
        self.put(self.home / 'Pictures/wallpapers/mine.png', 'personal')
        return uninstall.discover(self.home, self.directory)[-1]

    def test_restore_original_archive_edits_keep_unrelated_files(self):
        item = self.record()
        actions, _ = uninstall.file_plan(self.home, [item])
        archive = self.base / 'archive'
        uninstall.restore_files(self.home, archive, actions)
        self.assertEqual((self.home / '.config/hypr/hyprland.conf').read_text(), 'old 001')
        self.assertFalse((self.home / '.config/waybar').exists())
        self.assertEqual((archive / 'home/.config/hypr/hyprland.conf').read_text(), 'edited rice')
        self.assertEqual((archive / 'home/Pictures/wallpapers/rice.png').read_text(), 'edited wallpaper')
        self.assertEqual((self.home / 'Pictures/wallpapers/mine.png').read_text(), 'personal')
        self.assertTrue((item['backup'] / '.config/hypr/hyprland.conf').exists())

    def test_repeat_install_unwinds_to_first_snapshot(self):
        first = self.record('001')
        second = self.record('002')
        actions, _ = uninstall.file_plan(self.home, [first, second])
        uninstall.restore_files(self.home, self.base / 'archive', actions)
        self.assertEqual((self.home / '.config/hypr/hyprland.conf').read_text(), 'old 001')

    def test_missing_backup_aborts_before_any_mutation(self):
        item = self.record()
        shutil.rmtree(item['backup'] / '.config/hypr')
        with self.assertRaises(ValueError):
            uninstall.file_plan(self.home, [item])
        self.assertEqual((self.home / '.config/hypr/hyprland.conf').read_text(), 'edited rice')

    def test_traversal_and_symlink_parent_are_rejected(self):
        item = self.record()
        manifest = item['backup'] / 'deployment.json'
        for bad in ('../outside', '/tmp/outside', 'Pictures/wallpapers/../../outside'):
            state.write_json(manifest, {'managed': [], 'added': [{'path': bad}]})
            with self.subTest(path=bad), self.assertRaises(ValueError):
                uninstall.file_plan(self.home, [item])
        outside = self.base / 'outside'; outside.mkdir()
        shutil.rmtree(self.home / 'Pictures/wallpapers')
        (self.home / 'Pictures/wallpapers').symlink_to(outside)
        state.write_json(manifest, {'managed': [], 'added': [{'path': 'Pictures/wallpapers/file'}]})
        with self.assertRaises(ValueError):
            uninstall.file_plan(self.home, [item])

    def test_copy_failure_rolls_back_all_displaced_files(self):
        item = self.record()
        actions, _ = uninstall.file_plan(self.home, [item])
        with patch.object(uninstall, 'copy', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                uninstall.restore_files(self.home, self.base / 'archive', actions)
        self.assertEqual((self.home / '.config/hypr/hyprland.conf').read_text(), 'edited rice')
        self.assertTrue((self.home / '.config/waybar/config').exists())

    def test_legacy_restores_only_confirmed_backups_and_no_packages(self):
        backup = self.directory / 'backups/legacy'
        state.write_json(backup / 'installation.json', {})
        self.put(backup / '.config/hypr/hyprland.conf', 'legacy original')
        records = uninstall.discover(self.home, self.directory)
        actions, warnings = uninstall.file_plan(self.home, records)
        self.assertEqual(set(actions), {'.config/hypr'})
        self.assertTrue(warnings)
        self.assertEqual(uninstall.package_candidates(records, ['base']), ([], None))

    def test_packages_exclude_preexisting_os_upgrade_and_later_apps(self):
        first = self.record()
        second = self.record('002')
        second['before']['packages'] = ['base', 'hyprland', 'rice-dep', 'my-app']
        second['after']['baseline_packages'] = ['base', 'hyprland', 'rice-dep', 'my-app', 'upgrade2']
        second['after']['new_packages'] = ['another-dep']
        current = ['base', 'os-upgrade-dep', 'upgrade2', 'hyprland', 'rice-dep', 'my-app', 'another-dep', 'later-app']
        self.assertEqual(uninstall.package_candidates([first, second], current)[0], ['another-dep', 'hyprland', 'rice-dep'])

    def test_arch_removal_checks_shell_and_uses_no_cascade(self):
        with patch.object(state, 'installed_packages', return_value=['base', 'hyprland']), \
             patch.object(state, 'query', return_value='base'), patch.object(uninstall, 'run') as command:
            uninstall.remove_packages('arch', ['hyprland'], ['base', 'hyprland'])
        command.assert_called_once_with(['sudo', 'pacman', '-R', '--', 'hyprland'])

    def test_fedora_checks_exact_dependencies_and_protects_outside_packages(self):
        current = ['bash.x86_64', 'outside.noarch', 'hyprland.x86_64']
        with patch.object(state, 'installed_packages', return_value=current), \
             patch.object(state, 'query', return_value='bash.x86_64'), patch.object(uninstall, 'run') as command:
            uninstall.remove_packages('fedora', ['hyprland.x86_64'], current)
        self.assertEqual(command.call_args_list[0].args[0], ['sudo', 'rpm', '-e', '--test', '--', 'hyprland.x86_64'])
        native = command.call_args_list[1].args[0]
        self.assertIn('--setopt=protected_packages=bash,outside', native)
        self.assertIn('--no-autoremove', native)
        self.assertNotIn('-y', native)
        with patch.object(state, 'installed_packages', return_value=current), \
             patch.object(state, 'query', return_value='bash.x86_64'), \
             patch.object(uninstall, 'run', side_effect=subprocess.CalledProcessError(1, 'rpm')) as command:
            with self.assertRaises(subprocess.CalledProcessError):
                uninstall.remove_packages('fedora', ['hyprland.x86_64'], current)
            self.assertEqual(command.call_count, 1)

    def test_shell_package_cannot_be_removed(self):
        with patch.object(state, 'installed_packages', return_value=['zsh']), patch.object(state, 'query', return_value='zsh'), \
             patch.object(uninstall, 'run') as command:
            with self.assertRaises(ValueError):
                uninstall.remove_packages('arch', ['zsh'], ['zsh'])
            command.assert_not_called()

    def test_system_changes_restore_only_if_still_owned(self):
        item = self.record()
        item['before'].update(shell='/bin/bash', services={'sddm.service': 'disabled'}, settings={'gtk-theme': "'Old'"})
        item['after']['system'].update(shell='/bin/zsh', services={'sddm.service': 'enabled'}, settings={'gtk-theme': "'Rice'"})
        current = {'shell': '/bin/zsh', 'services': {'sddm.service': 'enabled'}, 'settings': {'gtk-theme': "'User choice'"}, 'default_target': 'graphical.target'}
        actions, warnings = uninstall.system_plan([item], current)
        self.assertEqual(actions, {'shell': '/bin/bash', 'service:sddm.service': 'disabled'})
        self.assertTrue(warnings)
        with patch.object(uninstall, 'run') as command:
            uninstall.restore_system({'service:sddm.service': 'disabled', 'service:gdm.service': 'enabled'})
        self.assertEqual(command.call_args_list[0].args[0], ['sudo', 'systemctl', 'disable', 'sddm.service'])
        self.assertEqual(command.call_args_list[1].args[0], ['sudo', 'systemctl', 'enable', 'gdm.service'])

    def test_dry_run_does_not_write_or_run_mutations(self):
        self.record()
        before = sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*'))
        env = {'HOME': str(self.home), 'XDG_STATE_HOME': str(self.home / '.local/state')}
        with patch.dict(os.environ, env), patch.object(sys, 'argv', ['uninstall.py', '--dry-run', '--packages']), \
             patch.object(state, 'system_state', return_value=self.current), \
             patch.object(state, 'installed_packages', return_value=['base', 'hyprland']), \
             patch.object(uninstall, 'run') as command, contextlib.redirect_stdout(io.StringIO()):
            uninstall.cli()
            command.assert_not_called()
        self.assertEqual(before, sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*')))

    def test_graphical_session_is_rejected_for_real_removal(self):
        with patch.dict(os.environ, {'WAYLAND_DISPLAY': 'wayland-1'}), self.assertRaises(ValueError):
            uninstall.ensure_logged_out()

    def test_theme_changed_by_launcher_is_restored_from_before_snapshot(self):
        item = self.record()
        state.write_json(item['backup'] / 'installation.json', {'cursor': True})
        item['before']['settings'] = {'gtk-theme': "'Adwaita'", 'cursor-theme': "'OldCursor'"}
        item['after']['system']['settings'] = dict(item['before']['settings'])
        current = dict(self.current)
        current['settings'] = {'gtk-theme': "'Flat-Remix-GTK-Blue-Dark'", 'cursor-theme': "'Bibata-Modern-Ice'"}
        actions, _ = uninstall.system_plan([item], current)
        self.assertEqual(actions['setting:gtk-theme'], "'Adwaita'")
        self.assertEqual(actions['setting:cursor-theme'], "'OldCursor'")

    def test_original_display_manager_remains_in_receipts_after_switch(self):
        with patch.object(state, 'service_state', return_value='disabled') as query, \
             patch.object(state, 'query', return_value=None):
            snapshot = state.system_state(['gdm.service'])
        self.assertIn('gdm.service', snapshot['services'])
        self.assertTrue(any(call.args == ('gdm.service',) for call in query.call_args_list))

    def test_original_symlink_is_restored_as_link_and_current_link_archived(self):
        item = self.record()
        source = item['backup'] / '.config/hypr'
        shutil.rmtree(source)
        source.symlink_to('/original/dotfiles/hypr')
        target = self.home / '.config/hypr'
        shutil.rmtree(target)
        target.symlink_to('/current/dotfiles/hypr')
        actions, _ = uninstall.file_plan(self.home, [item])
        archive = self.base / 'archive'
        uninstall.restore_files(self.home, archive, actions)
        self.assertEqual(os.readlink(target), '/original/dotfiles/hypr')
        self.assertEqual(os.readlink(archive / 'home/.config/hypr'), '/current/dotfiles/hypr')

    def test_failed_install_without_deployment_does_not_claim_user_files(self):
        item = self.record()
        (item['backup'] / 'deployment.json').unlink()
        item['before']['files'] = {'.zshrc': False, '.config/gtk-3.0/settings.ini': False}
        item['before']['oh_my_zsh_existed'] = False
        item['before']['options'] = {'zsh': 'true'}
        actions, _ = uninstall.file_plan(self.home, [item])
        self.assertEqual(actions, {})

    def test_fedora_inventory_excludes_rpm_public_key_pseudo_packages(self):
        result = subprocess.CompletedProcess([], 0, 'bash.x86_64\ngpg-pubkey.(none)\n', '')
        with patch.object(state.subprocess, 'run', return_value=result):
            self.assertEqual(state.installed_packages('fedora'), ['bash.x86_64'])

    def test_shell_menu_preview_has_safe_defaults_and_no_writes(self):
        self.record()
        mockbin = self.base / 'bin'; mockbin.mkdir()
        pacman = mockbin / 'pacman'
        pacman.write_text('#!/bin/sh\nprintf "base\\nhyprland\\n"\n')
        pacman.chmod(0o755)
        env = os.environ.copy()
        env.update(HOME=str(self.home), XDG_STATE_HOME=str(self.home / '.local/state'), PATH=str(mockbin) + ':' + env['PATH'])
        snapshot = sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*'))
        result = subprocess.run(['bash', str(ROOT / 'uninstall.sh'), '--dry-run'], input='\n\n', env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Пакеты будут сохранены', result.stdout)
        self.assertIn('Изменений нет', result.stdout)
        self.assertEqual(snapshot, sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*')))

    def test_full_flow_can_resume_package_failure_without_replacing_restored_files(self):
        item = self.record()
        env = {'HOME': str(self.home), 'XDG_STATE_HOME': str(self.home / '.local/state')}
        argv = ['uninstall.py', '--apply', '--packages']
        # All account, service and package calls are replaced with mocks.
        with patch.dict(os.environ, env), patch.object(sys, 'argv', argv), \
             patch.object(state, 'system_state', return_value=self.current), \
             patch.object(state, 'installed_packages', return_value=['base', 'hyprland']), \
             patch.object(uninstall, 'ensure_logged_out'), patch.object(uninstall.os, 'getuid', return_value=1000), \
             patch.object(uninstall, 'run'), patch.object(uninstall, 'remove_packages', side_effect=ValueError('package refusal')), \
             patch.object(state, 'COPR_FILE', self.base / 'no-copr'), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'package refusal'):
                uninstall.cli()
        self.assertTrue((item['record'] / 'uninstall-progress.json').exists())
        self.put(self.home / '.config/hypr/hyprland.conf', 'edited after interrupted removal')
        with patch.dict(os.environ, env), patch.object(sys, 'argv', argv), \
             patch.object(state, 'system_state', return_value=self.current), \
             patch.object(state, 'installed_packages', return_value=['base', 'hyprland']), \
             patch.object(uninstall, 'ensure_logged_out'), patch.object(uninstall.os, 'getuid', return_value=1000), \
             patch.object(uninstall, 'run'), patch.object(uninstall, 'remove_packages') as packages, \
             patch.object(state, 'COPR_FILE', self.base / 'no-copr'), contextlib.redirect_stdout(io.StringIO()):
            uninstall.cli()
        packages.assert_called_once()
        self.assertEqual((self.home / '.config/hypr/hyprland.conf').read_text(), 'edited after interrupted removal')
        self.assertTrue((item['record'] / 'uninstalled.json').exists())
        self.assertFalse((item['record'] / 'uninstall-progress.json').exists())
        self.assertEqual(uninstall.discover(self.home, self.directory), [])

    def test_empty_home_preview_is_harmless(self):
        env = os.environ.copy()
        env.update(HOME=str(self.home), XDG_STATE_HOME=str(self.home / '.local/state'))
        result = subprocess.run(['bash', str(ROOT / 'uninstall.sh'), '--dry-run'], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Изменений нет', result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
