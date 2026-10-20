#!/usr/bin/env python3
"""Install selected upstream theme assets into a staging HOME, never system paths."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request


def fetch(url, output):
    request = urllib.request.Request(url, headers={'User-Agent': 'arch-hyprland-ricing-installer'})
    with urllib.request.urlopen(request, timeout=60) as response, output.open('wb') as stream:
        shutil.copyfileobj(response, stream)


def install(output, cursor):
    manifest = json.loads(Path(__file__).with_name('assets.json').read_text())
    selections = {
        'gtk': [('Flat-Remix-GTK-Blue-Light', '.themes'), ('Flat-Remix-GTK-Blue-Dark', '.themes')],
        'icons': [('Flat-Remix-Blue-Light', '.icons'), ('Flat-Remix-Blue-Dark', '.icons')],
        'symbols': [('SymbolsNerdFont-Regular.ttf', '.local/share/fonts/rice-nerd-symbols')],
    }
    if cursor:
        selections['cursor'] = [('Bibata-Modern-Ice', '.icons')]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rice-assets-') as temporary:
        temporary = Path(temporary)
        for key, targets in selections.items():
            spec = manifest[key]
            archive_path = temporary / (key + '.tar')
            print(f'Загрузка оформления: {key}', flush=True)
            fetch(spec['url'], archive_path)
            with archive_path.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            if checksum != spec['sha256']:
                raise ValueError(f'SHA-256 mismatch: {key}')
            unpacked = temporary / key
            with tarfile.open(archive_path) as archive:
                archive.extractall(unpacked, filter='data')
            for name, parent in targets:
                matches = [path for path in unpacked.rglob(name) if path.name == name]
                if len(matches) != 1:
                    raise ValueError(f'Expected one asset {name}, found {len(matches)}')
                source = matches[0]
                destination = output / parent / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, destination, symlinks=True)
                else:
                    shutil.copy2(source, destination)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cursor', choices=('true', 'false'), required=True)
    args = parser.parse_args()
    install(args.output, args.cursor == 'true')
