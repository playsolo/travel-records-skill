#!/usr/bin/env python3
"""Probe installed resources and an isolated local runtime; no mailbox access."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

PROBE = 'import sys,jsonschema; assert sys.version_info >= (3,9); jsonschema.Draft202012Validator({"type":"object"}).validate({})'
RUNTIME_FORMAT = 'travel-records.private-runtime'
CORE_SCRIPTS = ('audit_coverage.py', 'demo.py', 'normalize_email.py', 'plan_followups.py',
                'read_reservation_jsonld.py', 'recognize_spending.py', 'reconcile_evidence.py',
                'resolve_stays.py', 'run_session.py', 'supervise_session.py', 'validate_expenses.py', 'validate_import.py')
CORE_REFERENCES = ('evidence-workflow.md', 'example.fotonest.json', 'execution-and-delivery.md',
                   'expenses-review.schema.json', 'extraction-workflow.md', 'mailbox-and-receipts.md',
                   'stay-acceptance.md', 'travel-import-v1.schema.json')
REQUIRED_FILES = {'plugin.json', 'LICENSE', 'skills/travel-records/SKILL.md',
                  'skills/travel-records/references/travel-import-v1.schema.json',
                  'skills/travel-records-setup/SKILL.md', 'skills/travel-records-setup/scripts/check_environment.py'} | {
                      'skills/travel-records/scripts/' + name for name in CORE_SCRIPTS} | {
                      'skills/travel-records/references/' + name for name in CORE_REFERENCES}


def resources(root):
    try:
        bundle = json.loads((root / 'checksums.json').read_text(encoding='utf-8'))
        files = bundle['files']
        if bundle['format'] != 'travel-records.plugin.bundle' or bundle['version'] != 1 or not isinstance(files, dict) or not REQUIRED_FILES <= files.keys():
            raise ValueError('invalid bundle')
        failures = []
        for name, expected in files.items():
            rel = PurePosixPath(name)
            if rel.is_absolute() or '..' in rel.parts or not rel.parts or '\\' in name:
                raise ValueError('invalid bundle path')
            target = root.joinpath(*rel.parts)
            if not target.resolve().is_relative_to(root.resolve()): raise ValueError('resource escapes package')
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                failures.append(name)
        return dict(status='ready' if not failures else 'incomplete', checked_files=len(files), failures=failures[:20])
    except (OSError, ValueError, KeyError, TypeError):
        return dict(status='unavailable', checked_files=0)


def writable(path):
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.travel-records-probe-', dir=path)
        try:
            with os.fdopen(fd, 'wb') as f: f.write(b'travel-records-probe')
            if Path(name).read_bytes() != b'travel-records-probe': raise ValueError('readback failed')
        finally:
            Path(name).unlink(missing_ok=True)
        return 'ready'
    except (OSError, ValueError):
        return 'unavailable'


def supports_helpers(executable):
    try:
        return subprocess.run([str(executable), '-I', '-c', PROBE], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def install_environment():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PIP_')}
    env['PIP_CONFIG_FILE'] = os.devnull  # Disable site/global config as well as user config.
    return env


def managed_prefix(executable, directory):
    try:
        result = subprocess.run([str(executable), '-I', '-c', 'import sys; print(sys.prefix)'],
                                capture_output=True, text=True, timeout=15)
        return result.returncode == 0 and Path(result.stdout.strip()).resolve() == directory.resolve()
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def pip_available(executable, env):
    try:
        return subprocess.run([str(executable), '-I', '-m', 'pip', '--isolated', '--version'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def runtime(workspace, prepare=False):
    managed = workspace / '.travel-records-runtime'
    marker = managed / '.owner.json'
    executable = managed / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if supports_helpers(sys.executable): return dict(status='ready', python_executable=sys.executable)
    if managed.exists():
        try:
            if managed.is_symlink() or json.loads(marker.read_text()).get('format') != RUNTIME_FORMAT:
                return dict(status='unmanaged_runtime')
        except (OSError, ValueError, AttributeError):
            return dict(status='unmanaged_runtime')
        if managed_prefix(executable, managed) and supports_helpers(executable): return dict(status='ready', python_executable=str(executable))
    if not prepare: return dict(status='dependency_missing')
    try:
        if not managed.exists():
            managed.mkdir(mode=0o700)
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as f: json.dump(dict(format=RUNTIME_FORMAT), f)
        env = install_environment()
        if not managed_prefix(executable, managed):
            subprocess.run([sys.executable, '-I', '-m', 'venv', '--without-pip', str(managed)], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, check=True, timeout=60, env=env)
        if not managed_prefix(executable, managed): return dict(status='invalid_runtime')
        if not pip_available(executable, env):
            subprocess.run([str(executable), '-I', '-m', 'ensurepip', '--upgrade'], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, check=True, timeout=60, env=env)
        subprocess.run([str(executable), '-I', '-m', 'pip', '--isolated', 'install', '--no-user', '--prefix', str(managed), '--index-url', 'https://pypi.org/simple',
                        '--only-binary=:all:', '--disable-pip-version-check', '--retries', '0', '--timeout', '20',
                        'jsonschema>=4.18,<5'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       check=True, timeout=180, env=env)
        if supports_helpers(executable): return dict(status='ready', python_executable=str(executable))
        return dict(status='dependency_missing')
    except (OSError, subprocess.SubprocessError):
        return dict(status='preparation_failed')


def check(root, workspace, prepare=False):
    package = resources(root)
    # Keep generated data and isolated environments outside the immutable bundle.
    if workspace.resolve().is_relative_to(root.resolve()):
        workspace_status = 'inside_plugin'
    else:
        workspace_status = writable(workspace)
    python_ok = sys.version_info >= (3, 9)
    result = dict(format='travel-records.setup.check', version=1, resources=package,
                  workspace=workspace_status, python_supported=python_ok,
                  gmail='requires_host_verification', file_delivery='requires_host_verification',
                  automatic_continuation='requires_host_adapter')
    result['runtime'] = (runtime(workspace, prepare) if python_ok and workspace_status == 'ready' and package['status'] == 'ready'
                         else dict(status='not_checked'))
    result['can_run_local_helpers'] = result['runtime']['status'] == 'ready'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--prepare', action='store_true', help='Prepare an isolated runtime if dependency checks fail')
    args = parser.parse_args()
    result = check(Path(__file__).resolve().parents[3], args.workspace, args.prepare)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['can_run_local_helpers'] else 2)


if __name__ == '__main__': main()
