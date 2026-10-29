"""Recover hash-pinned frontend inputs from the previously verified public release."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/release-inputs')
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / 'frontend-build/release.json').read_text())
    downloads = output / 'downloads'
    downloads.mkdir(exist_ok=True)
    names = ['multi-pop-rgds-rocknix-' + config['firmware_version'] + '.zip', 'multi-pop-rgds-source.zip']
    # The pinned inputs stay on this repository's old releases until a release_repo field moves them elsewhere.
    repo = config.get('release_repo', 'ballardcm/multi-pop-rgds')
    subprocess.run(['gh', 'release', 'download', config['release_tag'], '--repo', repo,
                    '--dir', str(downloads), '--skip-existing', '--pattern', names[0], '--pattern', names[1]], check=True)
    members = [
        (names[0], 'multi-pop-rgds/frontend/emulationstation', 'emulationstation-aarch64', 'frontend'),
        (names[1], 'multi-pop-rgds-source/frontend-build/upstream-source.tar.gz', config['upstream_source']['asset'], 'upstream_source'),
        (names[1], 'multi-pop-rgds-source/frontend-build/SDL2-source.tar.gz', config['sdl_source']['asset'], 'sdl_source'),
        (names[1], 'multi-pop-rgds-source/frontend-build/pugixml-source.tar.gz', config['pugixml_source']['asset'], 'pugixml_source'),
    ]
    for archive, member, name, key in members:
        with zipfile.ZipFile(downloads / archive) as source:
            data = source.read(member)
        if hashlib.sha256(data).hexdigest() != config[key]['sha256']:
            raise ValueError('Pinned release input mismatch: ' + key)
        (output / name).write_bytes(data)
        print('Verified', key, name)


if __name__ == '__main__':
    main()
