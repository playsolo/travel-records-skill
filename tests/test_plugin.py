"""Private packaging and setup tests; no network, mailbox or App installation."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import venv
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import package_plugin

SOURCE = Path(package_plugin.__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('travel_setup_check', SOURCE / 'plugin/skills/travel-records-setup/scripts/check_environment.py')
setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def bundle(self):
        result = package_plugin.package(SOURCE, self.root / 'marketplace')
        return Path(result['plugin_root']), result

    def test_bundle_relocates_and_runs_without_a_repository_download(self):
        plugin, result = self.bundle()
        relocated = self.root / 'installed'
        with zipfile.ZipFile(result['archive']) as z: z.extractall(relocated)
        script = relocated / 'skills/travel-records-setup/scripts/check_environment.py'
        out = subprocess.run([sys.executable, '-B', str(script), '--workspace', str(self.root / 'data')], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        check = json.loads(out.stdout)
        self.assertTrue(check['can_run_local_helpers'])
        self.assertEqual(check['gmail'], 'requires_host_verification')
        self.assertEqual(check['automatic_continuation'], 'requires_host_adapter')
        self.assertEqual((relocated / 'skills/travel-records/scripts/reconcile_evidence.py').read_bytes(),
                         (SOURCE / 'scripts/reconcile_evidence.py').read_bytes())
        catalog = json.loads(Path(result['marketplace_file']).read_text())
        location = Path(result['marketplace_root']) / catalog['plugins'][0]['source']['path']
        self.assertEqual(location.resolve(), plugin.resolve())

    def test_resource_tamper_missing_files_and_incomplete_manifest_block(self):
        plugin, _ = self.bundle()
        helper = plugin / 'skills/travel-records/scripts/run_session.py'
        helper.write_text('changed')
        self.assertFalse(setup.check(plugin, self.root / 'data')['can_run_local_helpers'])
        helper.unlink()
        self.assertEqual(setup.resources(plugin)['status'], 'incomplete')
        (plugin / 'checksums.json').write_text(json.dumps(dict(format='travel-records.plugin.bundle', version=1, files={'plugin.json':'invalid'})))
        self.assertEqual(setup.resources(plugin)['status'], 'unavailable')

    def test_existing_destination_and_workspace_files_are_preserved(self):
        existing = self.root / 'existing'; existing.mkdir(); (existing / 'user.json').write_text('keep')
        with self.assertRaises(FileExistsError): package_plugin.package(SOURCE, existing)
        self.assertEqual((existing / 'user.json').read_text(), 'keep')
        plugin, _ = self.bundle()
        user_file = self.root / 'data'; user_file.write_text('keep')
        self.assertEqual(setup.check(plugin, user_file)['workspace'], 'unavailable')
        self.assertEqual(user_file.read_text(), 'keep')

    def test_private_probe_does_not_write_into_bundle_or_leave_test_files(self):
        plugin, _ = self.bundle()
        before = sorted(p.relative_to(plugin) for p in plugin.rglob('*'))
        self.assertEqual(setup.check(plugin, plugin / 'data')['workspace'], 'inside_plugin')
        self.assertEqual(before, sorted(p.relative_to(plugin) for p in plugin.rglob('*')))
        workspace = self.root / 'data'
        setup.check(plugin, workspace)
        self.assertEqual(stat.S_IMODE(workspace.stat().st_mode), 0o700)
        self.assertEqual(list(workspace.iterdir()), [])

    def test_missing_dependency_is_reported_without_installing_on_probe(self):
        with patch.object(setup, 'supports_helpers', return_value=False), patch.object(setup.subprocess, 'run') as run:
            self.assertEqual(setup.runtime(self.root)['status'], 'dependency_missing')
            run.assert_not_called()

    def test_prepare_refuses_unowned_runtime_and_redacts_install_failure(self):
        runtime = self.root / '.travel-records-runtime'; runtime.mkdir(); (runtime / 'user.txt').write_text('keep')
        with patch.object(setup, 'supports_helpers', return_value=False), patch.object(setup.subprocess, 'run') as run:
            self.assertEqual(setup.runtime(self.root, True)['status'], 'unmanaged_runtime'); run.assert_not_called()
        self.assertEqual((runtime / 'user.txt').read_text(), 'keep')
        other = self.root / 'other'; other.mkdir()
        with patch.object(setup, 'supports_helpers', return_value=False), patch.object(setup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1,'pip',output='private-secret')):
            result = setup.runtime(other, True)
        self.assertEqual(result['status'], 'preparation_failed')
        self.assertNotIn('private-secret', json.dumps(result))

    def test_source_symlink_and_missing_runtime_reject_partial_packages(self):
        source = self.root / 'source'; shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns('__pycache__'))
        (source / 'references/link.md').symlink_to(SOURCE / 'SKILL.md')
        out = self.root / 'output'
        with self.assertRaises(ValueError): package_plugin.package(source, out)
        self.assertFalse(out.exists())
        (source / 'references/link.md').unlink()
        (source / 'scripts/resolve_stays.py').unlink()
        with self.assertRaises(ValueError): package_plugin.package(source, out)
        self.assertFalse(out.exists())

    def test_incomplete_owned_venv_repairs_pip_without_escaping_workspace(self):
        directory = self.root / '.travel-records-runtime'
        venv.EnvBuilder(with_pip=False).create(directory)
        (directory / '.owner.json').write_text(json.dumps(dict(format=setup.RUNTIME_FORMAT)))
        executable = directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        outside = self.root / 'outside'; config = self.root / 'pip.conf'
        config.write_text('[global]\ntarget = ' + str(outside) + '\n')
        real_run, real_supports = subprocess.run, setup.supports_helpers
        calls = []
        def run(argv, **kwargs):
            if 'install' in argv:
                calls.append((argv, kwargs['env']))
                return subprocess.CompletedProcess(argv, 0)
            return real_run(argv, **kwargs)
        def supports(path):
            return False if str(path) == sys.executable else real_supports(path)
        with patch.dict(os.environ, {'PIP_TARGET':str(outside), 'PIP_PREFIX':str(outside), 'PIP_CONFIG_FILE':str(config)}), patch.object(setup.subprocess, 'run', side_effect=run), patch.object(setup, 'supports_helpers', side_effect=supports):
            result = setup.runtime(self.root, True)
        self.assertEqual(result['status'], 'dependency_missing')  # Network install was intentionally not performed.
        self.assertEqual(len(calls), 1)
        argv, env = calls[0]
        self.assertEqual(argv[argv.index('--prefix')+1], str(directory))
        self.assertNotIn('PIP_TARGET', env); self.assertNotIn('PIP_PREFIX', env)
        self.assertEqual(env['PIP_CONFIG_FILE'], os.devnull)
        config_result = real_run([str(executable), '-I', '-m', 'pip', '--isolated', 'config', 'list'], env=env, capture_output=True, text=True)
        self.assertEqual(config_result.returncode, 0, config_result.stderr)
        self.assertNotIn(str(outside), config_result.stdout)
        self.assertFalse(outside.exists())
        self.assertTrue(setup.managed_prefix(executable, directory))

    def test_hidden_credentials_and_test_outputs_are_not_runtime_resources(self):
        source = self.root / 'source'; shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns('__pycache__'))
        (source / 'scripts/.env').write_text('secret')
        result = package_plugin.package(source, self.root / 'output')
        with zipfile.ZipFile(result['archive']) as z:
            names = z.namelist()
            self.assertFalse(any('/tests/' in n or n.endswith('.env') or '__pycache__' in n for n in names))
        self.assertNotIn('hooks', json.loads((Path(result['plugin_root'])/'plugin.json').read_text())['extensions']['com.openai'])


if __name__ == '__main__': unittest.main()
