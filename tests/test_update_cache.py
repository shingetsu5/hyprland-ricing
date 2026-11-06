import contextlib
import io
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'waybar/scripts'))
import updates_run as u
DETAILS = {'distro': 'Fedora', 'manager': 'DNF5', 'packages': [{'name': 'demo', 'current': '1', 'available': '2', 'source': 'Система'}], 'checked_at': '12:00'}

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, XDG_CACHE_HOME=self.directory.name)
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()
    def save(self, age=0):
        u.write_cache(dict(DETAILS, attempted_at=time.time()-age))
    def test_open_fresh_does_not_start_network(self):
        self.save()
        with patch.object(u, 'start_cache_refresh') as start, patch.object(u, 'package_details', side_effect=AssertionError('network')):
            self.assertEqual(u.cached_details()['packages'], DETAILS['packages'])
            start.assert_not_called()
    def test_stale_list_returned_while_background_starts(self):
        self.save(700)
        with patch.object(u, 'start_cache_refresh') as start:
            data = u.cached_details()
            self.assertEqual(data['packages'], DETAILS['packages'])
            self.assertTrue(data['refreshing'])
            self.assertFalse(data['pending'])
            start.assert_called_once_with(False)
    def test_missing_cache_is_pending_not_empty_success(self):
        with patch.object(u, 'start_cache_refresh'):
            data = u.cached_details()
            self.assertTrue(data['pending'])
            self.assertNotIn('packages', data)
    def test_error_preserves_last_success_and_does_not_retry_loop(self):
        self.save(700)
        with patch.object(u, 'package_details', side_effect=u.UpdateError('offline')):
            self.assertEqual(u.refresh_cache(), 1)
        with patch.object(u, 'start_cache_refresh') as start:
            data = u.cached_details()
            self.assertEqual(data['error'], 'offline')
            self.assertEqual(data['packages'], DETAILS['packages'])
            start.assert_not_called()
    def test_manual_refresh_recovers_error(self):
        self.save()
        data = u.read_cache(); data['error'] = 'offline'; u.write_cache(data)
        with patch.object(u, 'package_details', return_value=DETAILS.copy()) as collect:
            self.assertEqual(u.refresh_cache(force=True), 0)
            collect.assert_called_once()
        self.assertNotIn('error', u.read_cache())
    def test_panel_reuses_fresh_cache(self):
        self.save()
        with patch.object(u, 'package_details', side_effect=AssertionError('duplicate network')), patch('sys.argv', ['updates_run.py', '--count']), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(u.main(), 0)
        self.assertIn('1', output.getvalue())
    def test_parallel_refresh_only_collects_once(self):
        counter = Path(self.directory.name) / 'calls'
        def collect():
            with counter.open('a') as stream: stream.write('call\n')
            time.sleep(.15)
            return DETAILS.copy()
        with patch.object(u, 'package_details', side_effect=collect):
            processes = [multiprocessing.get_context('fork').Process(target=u.refresh_cache) for _ in range(4)]
            for process in processes: process.start()
            for process in processes:
                process.join(3)
                self.assertEqual(process.exitcode, 0)
        self.assertEqual(counter.read_text(), 'call\n')
        self.assertEqual(u.read_cache()['packages'], DETAILS['packages'])
    def test_damaged_cache_recovers(self):
        u.cache_directory().mkdir()
        (u.cache_directory() / 'packages.json').write_text('{bad')
        with patch.object(u, 'package_details', return_value=DETAILS.copy()):
            self.assertEqual(u.refresh_cache(), 0)
        self.assertEqual(u.read_cache()['packages'], DETAILS['packages'])

if __name__ == '__main__': unittest.main()
