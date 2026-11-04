import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


class SkillArchiveTests(unittest.TestCase):
    def test_archive_is_self_contained_and_runs_outside_the_repository(self):
        spec = importlib.util.spec_from_file_location('package_skill', ROOT / 'scripts' / 'package_skill.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            archive_path = module.package(temp / 'skill.zip')
            with ZipFile(archive_path) as archive:
                names = archive.namelist()
                self.assertIn('briefmint/SKILL.md', names)
                self.assertIn('briefmint/references/integration.md', names)
                self.assertFalse(any(name.endswith(('.sqlite3', '.pem', '.key', '.env')) for name in names))
                archive.extractall(temp / 'extracted')
            skill = temp / 'extracted' / 'briefmint'
            result = subprocess.run([sys.executable, str(skill / 'scripts' / 'run.py'),
                '--db', str(temp / 'private.sqlite3'), 'demo', '--input', str(skill / 'examples' / 'launch.json')],
                cwd=temp, capture_output=True, text=True, timeout=15, check=True)
            output = json.loads(result.stdout)
            self.assertEqual(output['beforePayment'], 402)
            self.assertEqual(output['afterPayment'], 200)
            self.assertTrue(output['idempotentReplay'])
            self.assertFalse(output['realMoney'])
