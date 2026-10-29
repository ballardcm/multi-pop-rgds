#!/usr/bin/env python3
"""Keep an activated Multi Pop RG DS on the latest release without restarting the frontend under the player.

`background` runs after each Multi Pop start: it confirms a just-applied update reached a running frontend, then
downloads and verifies any newer release and announces it. `check` does the same download at once when the player chooses
Check for updates in Theme Configuration, and reports the result either way. `apply` runs before the frontend starts and swaps a staged
release into place, rolling back when the new version fails to reach a running frontend.
"""

import argparse
import fcntl
import os
import urllib.parse
from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
# Releases now come from the multi-pop monorepo, which also publishes Thor and frontend-input releases, so only
# an RG DS theme tag (rgds-MM.DD.YY.N) is ever considered.
TAG = re.compile(r'rgds-(\d{2})\.(\d{2})\.(\d{2})\.(\d{1,3})')
ARCHIVE = re.compile(r'multi-pop-rgds-rocknix-[^/]+\.zip')
# A run of unrelated releases can push the newest RG DS one off the first page; a few pages bound the search.
RELEASE_PAGES = 3
# A new version that has not reached a running frontend after this many further starts is rolled back.
FAILED_STARTS_BEFORE_ROLLBACK = 2


@dataclass
class Config:
    theme: Path = Path('/roms/themes/multi-pop-rgds')
    state: Path = Path('/storage/.config/multi-pop-rgds')
    release_api: str = 'https://api.github.com/repos/ballardcm/multi-pop/releases?per_page=30'
    frontend_api: str = 'http://127.0.0.1:1234'
    verify_process: bool = True
    check_interval: float = 6 * 3600
    frontend_wait: float = 180
    # The HTTP API answers while the frontend is still loading, and a notice shown then is never seen.
    notify_delay: float = 30
    idle_wait: float = 6 * 3600
    installer: Path = field(default_factory=lambda: SCRIPT_DIR / 'update_theme.py')
    es_settings: Path = Path('/storage/.config/emulationstation/es_settings.cfg')

    @property
    def updates(self):
        return self.state / 'update'


def log(config, message):
    config.updates.mkdir(parents=True, exist_ok=True)
    path = config.updates / 'auto-update.log'
    # A small rolling log keeps a record for diagnosis without growing on the device.
    if path.exists() and path.stat().st_size > 100_000:
        path.replace(path.with_suffix('.log.old'))
    with path.open('a') as output:
        output.write(time.strftime('%Y-%m-%d %H:%M:%S ') + message + '\n')


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix('.tmp')
    staged.write_text(json.dumps(value, indent=2) + '\n')
    staged.replace(path)


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def installer(config):
    # The bundled updater owns the archive rules, so staging and applying validate exactly as a manual update does.
    spec = importlib.util.spec_from_file_location('multi_pop_update_theme', config.installer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def enabled(config):
    # Updates stay off until the player turns on UI Settings > Theme Configuration > Automatic updates.
    try:
        root = ET.parse(config.es_settings).getroot()
    except (OSError, ET.ParseError):
        return False
    return any(node.get('name') == 'subset.autoupdate' and node.get('value') == 'on' for node in root.iter('string'))


def reject(config, tag):
    rejected = read_json(config.updates / 'rejected.json', [])
    if tag not in rejected:
        write_json(config.updates / 'rejected.json', rejected + [tag])


def discard_staged(config):
    for name in ('staged.json', 'staged.zip'):
        (config.updates / name).unlink(missing_ok=True)


def firmware_revision(path):
    return (read_json(path, {}) or {}).get('firmware_revision')


def release_version(value):
    # Releases before numbering count as version 0, so any numbered release replaces them.
    version = (value or {}).get('version', 0) if isinstance(value, dict) else 0
    return version if isinstance(version, int) and not isinstance(version, bool) and version >= 0 else 0


# Applying, before the frontend starts.

def rollback(config, pending):
    backup = Path(pending['backup'])
    if not backup.is_dir():
        raise RuntimeError('The previous theme backup is missing; the installed theme was kept.')
    failed = config.theme.parent / ('.multi-pop-rgds-failed-' + pending['tag'])
    if failed.exists():
        shutil.rmtree(failed)
    config.theme.rename(failed)
    backup.rename(config.theme)
    reject(config, pending['tag'])
    (config.updates / 'pending.json').unlink()
    log(config, 'Rolled back ' + pending['tag'] + ' after it did not reach a running frontend.')


def apply(config):
    pending = read_json(config.updates / 'pending.json')
    if pending:
        # Every start since applying that did not confirm a running frontend counts toward a rollback.
        pending['starts'] = pending.get('starts', 0) + 1
        if pending['starts'] > FAILED_STARTS_BEFORE_ROLLBACK:
            rollback(config, pending)
        else:
            write_json(config.updates / 'pending.json', pending)
        return
    staged = read_json(config.updates / 'staged.json')
    if not staged:
        return
    # A download staged before updates were turned off is dropped rather than installed; one the player asked for stays.
    if not enabled(config) and not staged.get('manual'):
        discard_staged(config)
        log(config, 'Discarded staged ' + str(staged.get('tag')) + ' because automatic updates are off.')
        return
    archive = config.updates / 'staged.zip'
    stage = None
    backup = None
    try:
        if not archive.is_file() or file_sha(archive) != staged['sha256']:
            raise RuntimeError('The staged archive no longer matches its checksum.')
        if not config.theme.is_dir() or config.theme.is_symlink():
            raise RuntimeError('The installed theme is not at the supported location.')
        stage = Path(tempfile.mkdtemp(prefix='.multi-pop-rgds-stage-', dir=config.theme.parent))
        stage.chmod(0o755)
        installer(config).unpack(archive, stage)
        if firmware_revision(stage / 'frontend/compatibility.json') != firmware_revision(config.theme / 'frontend/compatibility.json'):
            raise RuntimeError('The update targets different firmware.')
        for name in ('start_es_rgds.sh', 'start_after_reboot.sh', 'multi_pop_rgds_common.sh'):
            current = config.theme / 'scripts' / name
            if current.exists() and file_sha(stage / 'scripts' / name) != file_sha(current):
                raise RuntimeError('Startup helper changed; reinstall this release explicitly.')
        backup = config.theme.parent / ('.multi-pop-rgds-backup-' + time.strftime('%Y%m%dT%H%M%S'))
        config.theme.rename(backup)
        stage.rename(config.theme)
        stage = None
        write_json(config.updates / 'pending.json', {'tag': staged['tag'], 'sha256': staged['sha256'], 'version': staged.get('version'), 'display_version': staged.get('display_version'), 'backup': str(backup), 'starts': 0})
        log(config, 'Applied ' + staged['tag'] + '; the previous theme is at ' + str(backup) + '.')
    except Exception as error:
        if backup is not None and backup.exists() and not config.theme.exists():
            backup.rename(config.theme)
        reject(config, staged.get('tag', 'unknown'))
        log(config, 'Did not apply ' + str(staged.get('tag')) + ': ' + str(error))
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        discard_staged(config)


# Confirming and staging, after the frontend starts.

def frontend_running(config):
    deadline = time.monotonic() + config.frontend_wait
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(config.frontend_api + '/runningGame', timeout=5):
                if config.verify_process:
                    pids = subprocess.check_output(['pidof', 'emulationstation'], text=True).split()
                    if len(pids) != 1 or Path('/proc/' + pids[0] + '/exe').resolve() != (config.theme / 'frontend/emulationstation').resolve():
                        time.sleep(3)
                        continue
                    report = read_json(config.theme / 'frontend/compatibility.json', {}) or {}
                    if file_sha(config.theme / 'frontend/emulationstation') != report.get('artifact_sha256'):
                        return False
                return True
        except (OSError, subprocess.CalledProcessError):
            time.sleep(3)
    return False


def confirm(config):
    pending = read_json(config.updates / 'pending.json')
    if not pending:
        return
    write_json(config.updates / 'installed.json', {'tag': pending['tag'], 'sha256': pending['sha256'], 'version': pending.get('version')})
    (config.updates / 'pending.json').unlink()
    # One backup stays for manual recovery; older ones would otherwise accumulate with every update.
    keep = Path(pending['backup']).name
    for old in config.theme.parent.glob('.multi-pop-rgds-backup-*'):
        if old.name != keep and old.is_dir():
            shutil.rmtree(old)
    log(config, 'Confirmed ' + pending['tag'] + ' is running.')
    version = pending.get('display_version') or (read_json(config.theme / 'version.json', {}) or {}).get('display_version') or pending.get('version')
    notify(config, 'Multi Pop updated' + (' to version ' + str(version) if version else '') + '.')


def idle(config):
    try:
        with urllib.request.urlopen(config.frontend_api + '/isIdle', timeout=5) as response:
            return json.load(response) == [True]
    except (OSError, ValueError):
        return False


def notify(config, message, delay=None):
    # A message box needs a press to close, so it waits until no game, scrape or install is running.
    time.sleep(config.notify_delay if delay is None else delay)
    deadline = time.monotonic() + config.idle_wait
    while not idle(config):
        if time.monotonic() >= deadline:
            return
        time.sleep(10)
    try:
        request = urllib.request.Request(config.frontend_api + '/messagebox', data=message.encode(), method='POST')
        urllib.request.urlopen(request, timeout=5).close()
    except OSError:
        pass


def download(url, destination):
    request = urllib.request.Request(url, headers={'User-Agent': 'MultiPopRGDS-updater'})
    with urllib.request.urlopen(request, timeout=60) as source, destination.open('wb') as target:
        shutil.copyfileobj(source, target)


def next_page(config, response):
    # GitHub pages a release list with a Link header; only a page on the same host as the release API is followed.
    for part in (response.headers.get('Link') or '').split(','):
        match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="?next"?\s*', part)
        if match:
            url = urllib.parse.urljoin(config.release_api, match.group(1))
            here, there = urllib.parse.urlsplit(config.release_api), urllib.parse.urlsplit(url)
            return url if (here.scheme, here.netloc) == (there.scheme, there.netloc) else None
    return None


def latest_release(config):
    """Return the tag and assets of the newest published RG DS release, or None when there is none."""
    url = config.release_api
    best = None
    for _ in range(RELEASE_PAGES):
        request = urllib.request.Request(url, headers={'User-Agent': 'MultiPopRGDS-updater', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=20) as response:
            releases = json.load(response)
            url = next_page(config, response)
        # The relay and an update-source override may serve a single release rather than a list.
        if isinstance(releases, dict):
            releases = [releases]
        if not isinstance(releases, list):
            raise RuntimeError('The release list is not in the expected form.')
        for release in releases:
            if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
                continue
            match = TAG.fullmatch(str(release.get('tag_name', '')))
            if not match:
                continue
            assets = {asset.get('name'): asset.get('browser_download_url') for asset in release.get('assets', []) if isinstance(asset, dict)}
            if 'SHA256SUMS' not in assets or not any(name and ARCHIVE.fullmatch(name) for name in assets):
                continue
            # The tag's own date and revision decide which is newest, since the API lists by creation time.
            mm, dd, yy, revision = (int(group) for group in match.groups())
            key = (yy, mm, dd, revision)
            if best is None or key > best[0]:
                best = (key, release['tag_name'], assets)
        if best is not None or url is None:
            break
    return None if best is None else best[1:]


def installed_matches(config, manifest):
    for name, expected in manifest.items():
        path = config.theme / name
        if not path.is_file() or file_sha(path) != expected:
            return False
    return True


def stage_latest(config, manual=False):
    marker = config.updates / 'last-check'
    if not manual and marker.exists() and time.time() - marker.stat().st_mtime < config.check_interval:
        return
    config.updates.mkdir(parents=True, exist_ok=True)
    marker.touch()
    latest = latest_release(config)
    if latest is None:
        # Before the first monorepo release there is nothing to install, which is being up to date rather than a failure.
        log(config, 'No RG DS release is published yet.')
        return
    tag, assets = latest
    known = {(read_json(config.updates / name, {}) or {}).get('tag') for name in ('installed.json', 'staged.json', 'pending.json')}
    if tag in known or tag in read_json(config.updates / 'rejected.json', []):
        return
    with tempfile.TemporaryDirectory(dir=config.updates) as work:
        work = Path(work)
        if 'SHA256SUMS' not in assets:
            raise RuntimeError(tag + ' has no SHA256SUMS.')
        download(assets['SHA256SUMS'], work / 'SHA256SUMS')
        sums = {}
        for line in (work / 'SHA256SUMS').read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and re.fullmatch(r'[0-9a-f]{64}', parts[0]):
                sums[parts[1].lstrip('*')] = parts[0]
        names = [name for name in sums if name.startswith('multi-pop-rgds-rocknix-') and name.endswith('.zip') and name in assets]
        if len(names) != 1:
            raise RuntimeError(tag + ' does not have exactly one installable archive.')
        archive = work / 'release.zip'
        download(assets[names[0]], archive)
        digest = file_sha(archive)
        if digest != sums[names[0]]:
            raise RuntimeError(tag + ' archive does not match SHA256SUMS.')
        with zipfile.ZipFile(archive) as opened:
            manifest = installer(config).read_manifest(opened)
            candidate = json.loads(opened.read('multi-pop-rgds/frontend/compatibility.json'))
            try:
                version_data = json.loads(opened.read('multi-pop-rgds/version.json'))
                version = release_version(version_data)
            except (KeyError, ValueError):
                version_data = {}
                version = 0
        if installed_matches(config, manifest):
            write_json(config.updates / 'installed.json', {'tag': tag, 'sha256': digest, 'version': version})
            log(config, 'Recorded ' + tag + ' as already installed.')
            return
        # Only a strictly newer release installs automatically; going back to an older one is left to a manual update.
        installed = release_version(read_json(config.theme / 'version.json'))
        if version <= installed:
            reject(config, tag)
            log(config, 'Skipped ' + tag + ': version ' + str(version) + ' is not newer than installed version ' + str(installed) + '.')
            return
        # An update never moves the theme to a frontend built for different firmware.
        if not candidate.get('firmware_revision') or candidate.get('firmware_revision') != firmware_revision(config.theme / 'frontend/compatibility.json'):
            reject(config, tag)
            log(config, 'Skipped ' + tag + ': it targets different firmware.')
            return
        archive.replace(config.updates / 'staged.zip')
        write_json(config.updates / 'staged.json', {'tag': tag, 'sha256': digest, 'version': version, 'display_version': version_data.get('display_version', str(version)), 'manual': manual})
    log(config, 'Staged ' + tag + ' (version ' + str(version) + ').')
    if not manual:
        notify(config, 'Multi Pop update ready. It installs the next time EmulationStation starts.')


def background(config):
    if not frontend_running(config):
        log(config, 'The frontend did not start; any applied update stays pending.')
        return
    confirm(config)
    if not enabled(config):
        return
    try:
        stage_latest(config)
    except Exception as error:
        log(config, 'Update check failed: ' + str(error))


def check(config):
    # The player is looking at the menu, so the answer appears at once whatever the setting or the last check time.
    try:
        stage_latest(config, manual=True)
    except Exception as error:
        log(config, 'Update check failed: ' + str(error))
        notify(config, 'Could not check for Multi Pop updates. Check the Wi-Fi connection and try again.', delay=0)
        return
    staged = read_json(config.updates / 'staged.json')
    if staged:
        message = 'Multi Pop version ' + str(staged.get('display_version') or staged.get('version')) + ' is ready. It installs the next time EmulationStation starts.'
    else:
        message = 'Multi Pop is up to date (version ' + str((read_json(config.theme / 'version.json', {}) or {}).get('display_version') or release_version(read_json(config.theme / 'version.json'))) + ').'
    notify(config, message, delay=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('apply', 'background', 'check'))
    args = parser.parse_args()
    config = Config()
    source = read_json(config.state / 'update-source.json', {}) or {}
    if source.get('release_api'):
        parsed = urllib.parse.urlsplit(source['release_api'])
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', '::1')):
            raise RuntimeError('Update sources require HTTPS or an SSH-forwarded loopback endpoint.')
        config.release_api = source['release_api']
    config.updates.mkdir(parents=True, exist_ok=True)
    lock = (config.updates / 'process.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log(config, 'Another update operation is running.')
        return 0
    try:
        {'apply': apply, 'background': background, 'check': check}[args.command](config)
    except Exception as error:
        # Startup must continue whatever happens here, so a failure is only recorded.
        log(config, args.command + ' failed: ' + str(error))
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
