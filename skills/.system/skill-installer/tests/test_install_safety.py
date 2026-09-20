import importlib.util
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('installer', SCRIPTS / 'install-skill-from-github.py')
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)

class InstallSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.src = self.repo / 'skills/demo'
        self.src.mkdir(parents=True)
        (self.src / 'SKILL.md').write_text('demo')
        self.external = self.root / 'outside'
        self.external.mkdir()
        (self.external / 'marker').write_text('EXTERNAL-MARKER')
        self.dest = self.root / 'installed/demo'

    def copy(self):
        installer._copy_skill(str(self.src), str(self.dest), str(self.repo))

    def test_nested_symlink_matrix_leaves_no_destination(self):
        for target in (self.external / 'marker', self.external, self.src / 'SKILL.md', self.root / 'missing'):
            with self.subTest(target=target):
                link = self.src / 'link'
                link.symlink_to(target)
                with self.assertRaises(installer.InstallError):
                    self.copy()
                self.assertFalse(self.dest.exists())
                link.unlink()
        self.assertEqual('EXTERNAL-MARKER', (self.external / 'marker').read_text())

    def test_root_and_ancestor_symlinks_rejected(self):
        for link, target, suffix in ((self.repo / 'alias', self.src, ''),
                                     (self.repo / 'external', self.external, 'nested')):
            (self.external / 'nested').mkdir(exist_ok=True)
            (self.external / 'nested/SKILL.md').write_text('external')
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(installer.InstallError):
                installer._copy_skill(str(link / suffix), str(self.dest), str(self.repo))
        self.assertFalse(self.dest.exists())

    def test_normal_copy_and_existing_dangling_destination(self):
        self.copy()
        self.assertEqual('demo', (self.dest / 'SKILL.md').read_text())
        with self.assertRaises(installer.InstallError):
            self.copy()
        other = self.dest.parent / 'dangling'
        other.symlink_to(self.root / 'missing')
        with self.assertRaises(installer.InstallError):
            installer._copy_skill(str(self.src), str(other), str(self.repo))
        self.assertTrue(other.is_symlink())

    def test_git_install_entrypoint_rejects_external_link(self):
        (self.src / 'secret').symlink_to(self.external / 'marker')
        with patch.object(installer, '_prepare_repo', return_value=str(self.repo)):
            result = installer.main(['--repo', 'test/repo', '--path', 'skills/demo',
                                     '--method', 'git', '--dest', str(self.dest.parent)])
        self.assertEqual(1, result)
        self.assertFalse(self.dest.exists())

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX special file')
    def test_fifo_is_rejected_without_reading(self):
        os.mkfifo(self.src / 'fifo')
        with self.assertRaises(installer.InstallError):
            self.copy()

    def test_system_temp_alias_above_repo_is_not_a_skill_symlink(self):
        alias = self.root / 'temp-alias'
        alias.symlink_to(self.repo, target_is_directory=True)
        installer._copy_skill(str(alias / 'skills/demo'), str(self.dest), str(alias))
        self.assertEqual('demo', (self.dest / 'SKILL.md').read_text())
