"""Update transport and conflict handling; package operations are always mocked."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'waybar/scripts'))
import updates_run as updates
import updates_fedora as fedora


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        # Tests must never inspect the host's DNF repositories.
        self.sources = patch.object(fedora, 'repository_sources', return_value={})
        self.sources.start()
        self.addCleanup(self.sources.stop)

    def test_arch_details_keep_repo_and_aur_versions(self):
        rows = [('pacman', 'waybar 0.13 -> 0.14'), ('AUR', 'custom-widget 1.0-1 -> 1.1-2')]
        with patch.object(updates, 'distro', return_value='arch'), patch.object(updates, 'collect_updates', return_value=rows):
            data = updates.package_details()
        self.assertEqual(data['packages'][0], {'name': 'waybar', 'current': '0.13', 'available': '0.14', 'source': 'Система'})
        self.assertEqual(data['packages'][1]['source'], 'AUR')
        with patch.object(updates, 'distro', return_value='arch'), patch.object(updates, 'collect_updates', return_value=[('AUR', 'unknown format')]):
            with self.assertRaises(updates.UpdateError):
                updates.package_details()

    def test_fedora_details_include_installed_version_and_epoch(self):
        result = subprocess.CompletedProcess([], 0, 'waybar.x86_64\t0:0.13-1.fc44\nother.noarch\t2:3.0-1\n', '')
        with patch.object(updates, 'distro', return_value='fedora'), \
             patch.object(updates, 'collect_updates', return_value=[('DNF', 'waybar.x86_64 → 0.14-1.fc44')]), \
             patch.object(updates.subprocess, 'run', return_value=result):
            data = updates.package_details()
        self.assertEqual(data['packages'][0]['current'], '0.13-1.fc44')
        self.assertEqual(data['packages'][0]['available'], '0.14-1.fc44')

    def test_json_failure_is_visible_to_window_and_never_installs(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary, \
             patch.dict(os.environ, XDG_CACHE_HOME=temporary), \
             patch.object(updates, 'package_details', side_effect=updates.UpdateError('No network')), \
             patch.object(updates, 'launch_upgrade') as launch:
            self.assertEqual(updates.refresh_cache(), 1)
            with patch.object(sys, 'argv', ['updates_run.py', '--json']), contextlib.redirect_stdout(output):
                self.assertEqual(updates.main(), 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data['error'], 'No network')
        self.assertFalse(data['pending'])
        self.assertNotIn('packages', data)
        launch.assert_not_called()

    def test_launch_detaches_terminal_and_does_not_supply_automatic_confirmation(self):
        with patch.object(updates.shutil, 'which', return_value='/usr/bin/kitty'), \
             patch.object(updates.subprocess, 'Popen') as launch:
            self.assertEqual(updates.launch_upgrade(), 0)
        command = launch.call_args.args[0]
        self.assertEqual(command[0], 'kitty')
        self.assertEqual(command[-1], '--upgrade')
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        self.assertNotIn('--assumeyes', command)
        self.assertNotIn('sudo', command)

    def test_closed_conflict_dialog_defaults_to_stop(self):
        with patch.object(updates.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(updates, 'gui_environment', return_value={}):
            self.assertEqual(updates.request_dialog(['Stop', 'Skip'], 'Conflict'), 'Stop')

    def test_dialog_reply_accepts_only_offered_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / 'request.json'
            request.write_text(json.dumps({'message': 'Conflict', 'options': ['Stop', 'Skip']}))
            with patch.object(sys, 'argv', ['updates_run.py', '--dialog-answer', str(request), '--index', '1']):
                self.assertEqual(updates.main(), 0)
            self.assertEqual(json.loads(request.with_name('reply.json').read_text()), {'index': 1})
            with patch.object(sys, 'argv', ['updates_run.py', '--dialog-answer', str(request), '--index', '5']):
                with self.assertRaises(updates.UpdateError):
                    updates.main()

    def test_fedora_does_not_skip_conflicts_without_explicit_choice(self):
        failure = 'Failed to resolve the transaction\ncannot install the best update candidate for package example-1-1.x86_64'
        with patch.object(fedora, 'run_logged', return_value=(1, failure)) as execute, \
             patch.object(fedora, 'dialog', return_value=fedora.STOP) as ask, patch.object(fedora, 'notify'), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fedora.update([], {'example.x86_64'}, io.StringIO()), 1)
        self.assertEqual(execute.call_count, 1)
        self.assertIn('--assumeno', execute.call_args.args[0])
        self.assertEqual(ask.call_args.args[0], [fedora.STOP, 'Пропустить example.x86_64', fedora.RETRY])

    def test_fedora_explicit_exclusion_keeps_strict_flags_and_log(self):
        failure = 'Failed to resolve the transaction\ncannot install the best update candidate for package example-1-1.x86_64'
        plan = 'Transaction Summary:\nOperation aborted by the user.'
        log = io.StringIO()
        with patch.object(fedora, 'run_logged', side_effect=[(1, failure), (1, plan), (0, 'Done')]) as execute, \
             patch.object(fedora, 'dialog', return_value='Пропустить example.x86_64'), \
             patch.object(fedora, 'notify'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fedora.update([], {'example.x86_64'}, log), 0)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertFalse(any(arg.startswith('--exclude=') for arg in commands[0]))
        for command in commands[1:]:
            self.assertIn('--exclude=example.x86_64', command)
            self.assertIn('--best', command)
            self.assertIn('--setopt=skip_broken=False', command)
            self.assertIn('--setopt=assumeyes=False', command)
        self.assertNotIn('--assumeno', commands[-1])
        self.assertIn('--setopt=max_parallel_downloads=10', commands[-1])
        self.assertIn('--setopt=max_downloads_per_mirror=5', commands[-1])
        self.assertIn('USER SKIPPED PACKAGE: example.x86_64', log.getvalue())

    def test_fedora_never_offers_exclusions_after_real_transaction_failure(self):
        with patch.object(fedora, 'run_logged', side_effect=[(1, 'Transaction Summary:\nOperation aborted by the user.'), (1, 'RPM failure')]), \
             patch.object(fedora, 'dialog', return_value=fedora.STOP) as ask, \
             patch.object(fedora, 'notify'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fedora.update([], set(), io.StringIO()), 1)
        self.assertEqual(ask.call_args.args[0], [fedora.STOP, fedora.RETRY])

    def test_repository_error_matches_exact_source_not_shared_host(self):
        sources = {'free': ['https://mirror.test/metalink?repo=free'],
                   'nonfree': ['https://mirror.test/metalink?repo=nonfree']}
        error = 'Curl error (28): https://mirror.test/metalink?repo=free [timeout]'
        self.assertEqual(fedora.problem_repositories(error, sources, set()), ['free'])
        self.assertEqual(fedora.problem_repositories(error, sources, {'free'}), [])

    def test_explicit_repository_skip_rechecks_dependencies_and_keeps_strict_flags(self):
        failure = "Failed to download metadata for repo 'free'"
        plan = 'Transaction Summary:\nOperation aborted by the user.'
        log = io.StringIO()
        with patch.object(fedora, 'run_logged', side_effect=[(1, failure), (1, plan), (0, 'Done')]) as execute, \
             patch.object(fedora, 'dialog', return_value='Пропустить репозиторий free'), \
             patch.object(fedora, 'notify'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fedora.update([], set(), log, sources={'free': []}), 0)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertNotIn('--disable-repo=free', commands[0])
        self.assertIn('--assumeno', commands[1])
        for command in commands[1:]:
            self.assertIn('--disable-repo=free', command)
            self.assertIn('--setopt=skip_broken=False', command)
        self.assertIn('USER SKIPPED REPOSITORY: free', log.getvalue())

    def test_download_skip_is_only_offered_before_transaction(self):
        plan = 'Transaction Summary:\nOperation aborted by the user.'
        failure = 'Failed to download packages\nCannot download example-1-1.x86_64.rpm:'
        for marker in ('', 'Running transaction', 'Preparing transaction', 'RPM transaction', 'Running scriptlet'):
            with self.subTest(marker=marker), \
                 patch.object(fedora, 'run_logged', side_effect=[(1, plan), (1, failure + '\n' + marker)]), \
                 patch.object(fedora, 'dialog', return_value=fedora.STOP) as ask, \
                 patch.object(fedora, 'notify'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fedora.update([], set(), io.StringIO()), 1)
                choices = ask.call_args.args[0]
                self.assertEqual('Пропустить example.x86_64' in choices, not bool(marker))

    def test_retry_after_download_skip_runs_a_new_preflight(self):
        plan = 'Transaction Summary:\nOperation aborted by the user.'
        failure = 'Failed to download packages\nCannot download example-1-1.x86_64.rpm:'
        with patch.object(fedora, 'run_logged', side_effect=[(1, plan), (1, failure), (1, plan), (0, 'Done')]) as execute, \
             patch.object(fedora, 'dialog', return_value='Пропустить example.x86_64'), \
             patch.object(fedora, 'notify'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fedora.update([], set(), io.StringIO()), 0)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertIn('--assumeno', commands[2])
        self.assertIn('--exclude=example.x86_64', commands[2])
        self.assertIn('--exclude=example.x86_64', commands[3])


if __name__ == '__main__':
    unittest.main()
