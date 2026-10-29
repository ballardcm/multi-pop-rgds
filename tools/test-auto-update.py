#!/usr/bin/env python3
"""Exercise the RG DS auto-updater against a local stand-in for GitHub and the frontend API."""

import hashlib
import http.server
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('auto_update', ROOT / 'multi-pop-rgds/scripts/auto_update.py')
auto_update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto_update)

FIRMWARE = 'firmware-a'
TAG = 'rgds-10.29.26.1'


def theme_files(version, firmware=FIRMWARE, number=None):
    number = {'old': 1, 'new': 2}.get(version, 3) if number is None else number
    return {
        'theme.xml': ('<theme version="' + version + '"/>').encode(),
        'version.json': json.dumps({'version': number}).encode(),
        'frontend/emulationstation': b'\x7fELF frontend ' + version.encode(),
        'frontend/compatibility.json': json.dumps({'firmware_revision': firmware}).encode(),
        'scripts/start_es_rgds.sh': b'#!/bin/bash\n',
    }


def archive_bytes(files):
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in files.items():
            archive.writestr('multi-pop-rgds/' + name, data)
        archive.writestr('install-manifest.json', json.dumps(manifest))
    return output.getvalue()


class Server(http.server.ThreadingHTTPServer):
    def __init__(self):
        super().__init__(('127.0.0.1', 0), Handler)
        self.routes = {}
        self.requests = []
        self.notifications = []
        self.extra_headers = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        body = self.server.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        for name, value in self.server.extra_headers.get(self.path, {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.server.notifications.append(self.rfile.read(int(self.headers['Content-Length'])).decode())
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.server = Server()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        base = 'http://127.0.0.1:%d' % self.server.server_address[1]
        self.themes = root / 'roms/themes'
        self.config = auto_update.Config(
            theme=self.themes / 'multi-pop-rgds', state=root / 'storage/.config/multi-pop-rgds',
            release_api=base + '/release', frontend_api=base, frontend_wait=2, notify_delay=0, verify_process=False,
            installer=ROOT / 'tools/install-multi-pop-theme.py', es_settings=root / 'es_settings.cfg')
        self.set_updates('on')
        for name, data in theme_files('old').items():
            path = self.config.theme / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.server.routes['/runningGame'] = b'{"msg":"NO GAME RUNNING"}'
        self.server.routes['/isIdle'] = b'[ true ]'
        self.publish(theme_files('new'))

    def set_updates(self, value):
        settings = '<?xml version="1.0"?>\n<config>\n\t<string name="ThemeSet" value="multi-pop-rgds" />\n'
        if value is not None:
            settings += '\t<string name="subset.autoupdate" value="' + value + '" />\n'
        self.config.es_settings.write_text(settings + '</config>\n')

    def entry(self, tag, path='', name='multi-pop-rgds-rocknix-20261001.zip', **flags):
        base = 'http://127.0.0.1:%d' % self.server.server_address[1]
        return {'tag_name': tag, 'draft': False, 'prerelease': False, **flags, 'assets': [
            {'name': name, 'browser_download_url': base + '/zip' + path},
            {'name': 'SHA256SUMS', 'browser_download_url': base + '/sums' + path}]}

    def publish(self, files, tag=TAG, sums_override=None, others=(), single=False):
        # The monorepo lists every system's releases together, so the real one is served among unrelated entries.
        archive = archive_bytes(files)
        name = 'multi-pop-rgds-rocknix-20261001.zip'
        digest = sums_override or hashlib.sha256(archive).hexdigest()
        release = self.entry(tag)
        self.server.routes.update({
            '/release': json.dumps(release if single else list(others) + [release]).encode(),
            '/zip': archive,
            '/sums': (digest + '  ' + name + '\n').encode(),
        })

    def decoys(self):
        # Each would be chosen if the filter let it through, and none of its downloads exist.
        return [
            self.entry('thor-12.31.26.9', '/thor', 'multi-pop-thor-rocknix-20261001.zip'),
            self.entry('rgds-frontend-12.31.26.1', '/frontend'),
            self.entry('rgds-12.31.26.1', '/prerelease', prerelease=True),
            self.entry('rgds-12.31.26.2', '/draft', draft=True),
            dict(self.entry('rgds-12.31.26.3', '/nosums'), assets=self.entry('rgds-12.31.26.3', '/nosums')['assets'][:1]),
            self.entry('build-0123456789ab', '/legacy'),
            self.entry('v0.3.3', '/semantic'),
        ]

    def installed_theme(self):
        return (self.config.theme / 'theme.xml').read_text()

    def updates(self, name):
        return auto_update.read_json(self.config.updates / name)

    def test_stage_apply_and_confirm(self):
        auto_update.background(self.config)
        self.assertEqual(self.updates('staged.json')['tag'], TAG)
        self.assertIn('installs the next time', self.server.notifications[0])
        self.assertIn('old', self.installed_theme())
        auto_update.apply(self.config)
        self.assertIn('new', self.installed_theme())
        self.assertIsNone(self.updates('staged.json'))
        backup = Path(self.updates('pending.json')['backup'])
        self.assertIn('old', (backup / 'theme.xml').read_text())
        (self.config.updates / 'last-check').unlink()
        auto_update.background(self.config)
        self.assertEqual(self.updates('installed.json')['tag'], TAG)
        self.assertEqual(self.server.notifications[-1], 'Multi Pop updated to version 2.')
        self.assertIsNone(self.updates('pending.json'))
        self.assertTrue(backup.is_dir())
        self.assertEqual(self.server.requests.count('/zip'), 1)

    def test_message_waits_for_an_idle_frontend(self):
        self.server.routes['/isIdle'] = b'[ false ]'
        self.config.idle_wait = 0
        auto_update.background(self.config)
        self.assertEqual(self.updates('staged.json')['tag'], TAG)
        self.assertEqual(self.server.notifications, [])

    def test_archive_not_matching_its_checksum_is_never_staged(self):
        self.publish(theme_files('new'), sums_override='0' * 64)
        auto_update.background(self.config)
        self.assertIsNone(self.updates('staged.json'))
        self.assertIn('does not match SHA256SUMS', (self.config.updates / 'auto-update.log').read_text())

    def test_release_for_other_firmware_is_skipped(self):
        self.publish(theme_files('new', firmware='firmware-b'))
        auto_update.background(self.config)
        self.assertIsNone(self.updates('staged.json'))
        self.assertEqual(self.updates('rejected.json'), [TAG])

    def test_matching_installation_is_recorded_without_staging(self):
        self.publish(theme_files('old'))
        auto_update.background(self.config)
        self.assertIsNone(self.updates('staged.json'))
        self.assertEqual(self.updates('installed.json')['tag'], TAG)

    def test_unconfirmed_update_rolls_back_and_is_skipped(self):
        auto_update.background(self.config)
        auto_update.apply(self.config)
        # The new frontend never answers, so each restart counts as a failed start.
        for start in range(auto_update.FAILED_STARTS_BEFORE_ROLLBACK + 1):
            auto_update.apply(self.config)
        self.assertIn('old', self.installed_theme())
        self.assertIsNone(self.updates('pending.json'))
        self.assertEqual(self.updates('rejected.json'), [TAG])
        self.assertTrue((self.themes / ('.multi-pop-rgds-failed-' + TAG)).is_dir())
        (self.config.updates / 'last-check').unlink()
        auto_update.background(self.config)
        self.assertIsNone(self.updates('staged.json'))

    def test_older_or_equal_release_is_never_staged(self):
        for number in (1, 0):
            with self.subTest(number=number):
                tag = 'rgds-01.01.26.%d' % number
                self.publish(theme_files('older', number=number), tag=tag)
                (self.config.updates / 'last-check').unlink(missing_ok=True)
                auto_update.background(self.config)
                self.assertIsNone(self.updates('staged.json'))
                self.assertIn(tag, self.updates('rejected.json'))
                self.assertIn('old', self.installed_theme())

    def test_numbered_release_replaces_an_unnumbered_installation(self):
        (self.config.theme / 'version.json').unlink()
        auto_update.background(self.config)
        self.assertEqual(self.updates('staged.json')['version'], 2)

    def test_manual_check_stages_while_updates_are_off(self):
        self.set_updates(None)
        auto_update.background(self.config)
        auto_update.check(self.config)
        self.assertIn('version 2 is ready', self.server.notifications[-1])
        auto_update.apply(self.config)
        self.assertIn('new', self.installed_theme())

    def test_manual_check_reports_up_to_date(self):
        self.publish(theme_files('old'))
        auto_update.check(self.config)
        auto_update.check(self.config)
        self.assertEqual(self.server.requests.count('/release'), 2)
        self.assertEqual(self.server.notifications, ['Multi Pop is up to date (version 1).'] * 2)

    def test_manual_check_reports_a_failure(self):
        del self.server.routes['/release']
        auto_update.check(self.config)
        self.assertIn('Could not check', self.server.notifications[-1])

    def test_updates_are_off_unless_turned_on(self):
        for value in (None, 'off'):
            with self.subTest(value=value):
                self.set_updates(value)
                auto_update.background(self.config)
                self.assertNotIn('/release', self.server.requests)

    def test_turning_updates_off_discards_a_staged_release(self):
        auto_update.background(self.config)
        self.set_updates('off')
        auto_update.apply(self.config)
        self.assertIn('old', self.installed_theme())
        self.assertIsNone(self.updates('staged.json'))
        self.assertFalse((self.config.updates / 'staged.zip').exists())

    def test_other_systems_prereleases_drafts_and_old_tags_are_ignored(self):
        self.publish(theme_files('new'), others=self.decoys())
        auto_update.background(self.config)
        self.assertEqual(self.updates('staged.json')['tag'], TAG)
        self.assertFalse([path for path in self.server.requests if path.startswith(('/zip/', '/sums/'))])

    def test_newest_release_wins_regardless_of_order(self):
        older = [self.entry('rgds-10.29.25.9', '/a'), self.entry('rgds-09.30.26.5', '/b'), self.entry('rgds-10.29.26.0', '/c')]
        for others in (older, older[::-1]):
            with self.subTest(order=[entry['tag_name'] for entry in others]):
                self.publish(theme_files('new'), others=others)
                (self.config.updates / 'last-check').unlink(missing_ok=True)
                auto_update.background(self.config)
                self.assertEqual(self.updates('staged.json')['tag'], TAG)
                auto_update.discard_staged(self.config)

    def test_empty_list_is_up_to_date(self):
        for listing in ([], self.decoys()):
            with self.subTest(entries=len(listing)):
                self.server.routes['/release'] = json.dumps(listing).encode()
                auto_update.check(self.config)
                self.assertEqual(self.server.notifications[-1], 'Multi Pop is up to date (version 1).')
                self.assertIsNone(self.updates('staged.json'))

    def test_single_release_object_is_accepted(self):
        self.publish(theme_files('new'), single=True)
        auto_update.background(self.config)
        self.assertEqual(self.updates('staged.json')['tag'], TAG)

    def test_missing_repository_is_logged_and_startup_continues(self):
        del self.server.routes['/release']
        auto_update.background(self.config)
        self.assertIsNone(self.updates('staged.json'))
        self.assertIn('Update check failed: HTTP Error 404', (self.config.updates / 'auto-update.log').read_text())

    def test_next_page_is_followed_only_when_nothing_matched(self):
        base = 'http://127.0.0.1:%d' % self.server.server_address[1]
        self.publish(theme_files('new'))
        self.server.routes['/page2'] = self.server.routes['/release']
        self.server.routes['/release'] = json.dumps(self.decoys()).encode()
        self.server.extra_headers = {'/release': {'Link': '<' + base + '/page2>; rel="next", <' + base + '/page9>; rel="last"'}}
        auto_update.background(self.config)
        self.assertEqual(self.updates('staged.json')['tag'], TAG)
        # A matching first page ends the search there.
        self.server.routes['/release'] = self.server.routes['/page2']
        (self.config.updates / 'last-check').unlink()
        auto_update.discard_staged(self.config)
        requests = self.server.requests.count('/page2')
        auto_update.background(self.config)
        self.assertEqual(self.server.requests.count('/page2'), requests)

    def test_pages_are_bounded(self):
        base = 'http://127.0.0.1:%d' % self.server.server_address[1]
        self.server.routes['/release'] = b'[]'
        self.server.extra_headers = {'/release': {'Link': '<' + base + '/release>; rel="next"'}}
        auto_update.check(self.config)
        self.assertEqual(self.server.requests.count('/release'), auto_update.RELEASE_PAGES)
        self.assertIn('up to date', self.server.notifications[-1])

    def test_legacy302_accepts_date_release_and_confirms_label(self):
        (self.config.theme / 'version.json').write_text(json.dumps({'version': 302, 'display_version': '0.3.2'}))
        files = theme_files('new', number=20261021001)
        files['version.json'] = json.dumps({'version': 20261021001, 'display_version': '10.21.26.1'}).encode()
        self.publish(files, tag=TAG)
        auto_update.check(self.config)
        self.assertEqual(self.updates('staged.json')['version'], 20261021001)
        auto_update.apply(self.config)
        auto_update.confirm(self.config)
        self.assertEqual(self.updates('installed.json')['version'], 20261021001)
        self.assertEqual(self.server.notifications[-1], 'Multi Pop updated to version 10.21.26.1.')
        self.publish(theme_files('old', number=302), tag='rgds-10.30.26.1')
        auto_update.check(self.config)
        self.assertIsNone(self.updates('staged.json'))

    def test_changed_startup_script_refuses_apply(self):
        files = theme_files('new')
        files['scripts/start_es_rgds.sh'] += b'# changed launcher\n'
        self.publish(files)
        auto_update.background(self.config)
        auto_update.apply(self.config)
        self.assertIn('old', self.installed_theme())
        self.assertIn(TAG, self.updates('rejected.json'))

    def test_modified_staged_archive_preserves_installed_theme(self):
        auto_update.background(self.config)
        (self.config.updates / 'staged.zip').write_bytes(b'corrupt')
        auto_update.apply(self.config)
        self.assertIn('old', self.installed_theme())
        self.assertIn(TAG, self.updates('rejected.json'))

    def test_checks_are_rate_limited(self):
        self.publish(theme_files('old'))
        auto_update.background(self.config)
        auto_update.background(self.config)
        self.assertEqual(self.server.requests.count('/release'), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
