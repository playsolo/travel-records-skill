#!/usr/bin/env python3
"""Package the canonical skill for a local or Git-backed desktop marketplace."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import zipfile

RUNTIME_SUFFIXES = {'.md', '.json', '.yaml', '.yml', '.py', '.svg', '.png'}


def source_files(folder):
    for path in sorted(folder.rglob('*')):
        rel = path.relative_to(folder)
        if any(part.startswith('.') or part == '__pycache__' for part in rel.parts): continue
        if path.is_symlink(): raise ValueError('package source cannot contain symlinks')
        if path.is_file() and path.suffix in RUNTIME_SUFFIXES: yield path, rel


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def package(source, output, marketplace_name='fotonest-travel-private'):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', marketplace_name) or len(marketplace_name) > 64:
        raise ValueError('invalid marketplace name')
    source, output = Path(source).resolve(), Path(output).absolute()
    if output.resolve().is_relative_to(source): raise ValueError('output must be outside source')
    if output.exists() or output.is_symlink(): raise FileExistsError('output already exists')
    blueprint = source / 'plugin'
    manifest = json.loads((blueprint / 'plugin.json').read_text(encoding='utf-8'))
    if manifest['name'] != 'travel-records': raise ValueError('unexpected package identity')
    output.mkdir(mode=0o700, parents=True)
    try:
        plugin = output / 'plugins' / manifest['name']
        for path, rel in source_files(blueprint):
            target = plugin / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
        skill = plugin / 'skills' / 'travel-records'
        skill.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / 'SKILL.md', skill / 'SKILL.md')
        for folder in ['references', 'scripts', 'agents']:
            for path, rel in source_files(source / folder):
                if folder == 'scripts' and rel == Path('package_plugin.py'): continue
                target = skill / folder / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
        shutil.copy2(source / 'LICENSE', plugin / 'LICENSE')
        required = runpy.run_path(str(blueprint / 'skills/travel-records-setup/scripts/check_environment.py'))['REQUIRED_FILES']
        if any(not (plugin / p).is_file() for p in required): raise ValueError('incomplete runtime bundle')
        checksums = {p.relative_to(plugin).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(plugin.rglob('*')) if p.is_file()}
        write_json(plugin / 'checksums.json', dict(format='travel-records.plugin.bundle', version=1,
                   plugin_version=manifest['version'], files=checksums))
        display_name = 'FotoNest Travel · 私有内测' if marketplace_name == 'fotonest-travel-private' else marketplace_name
        marketplace = dict(name=marketplace_name, interface=dict(displayName=display_name),
            plugins=[dict(name=manifest['name'], source=dict(source='local', path='./plugins/' + manifest['name']),
                          policy=dict(installation='AVAILABLE', authentication='ON_INSTALL'), category='Productivity')])
        catalog = output / '.agents' / 'plugins' / 'marketplace.json'
        write_json(catalog, marketplace)
        archive = output / 'travel-records-private-plugin.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for path in sorted(plugin.rglob('*')):
                if path.is_file(): z.write(path, path.relative_to(plugin).as_posix())
        return dict(plugin_root=str(plugin), marketplace_root=str(output), marketplace_file=str(catalog),
                    archive=str(archive), version=manifest['version'], bundled_files=len(checksums))
    except Exception:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New private directory outside the source tree')
    parser.add_argument('--marketplace-name', default='fotonest-travel-private',
                        help='Local/Git catalog identity; does not publish to the OpenAI directory')
    args = parser.parse_args()
    try:
        result = package(Path(__file__).resolve().parents[1], args.output, args.marketplace_name)
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('INVALID: plugin packaging failed; use a complete source and a new output directory')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
