# SPDX-License-Identifier: MIT
import json
import tempfile
import unittest
from pathlib import Path
from helm_purifier import lock

class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'Chart.yaml').write_text('apiVersion: v2\nname: demo\nversion: 1.0.0\n')
        (self.root / 'Chart.lock').write_text('dependencies:\n- name: library\n  repository: https://example.org/charts\n  version: 1.2.3\ndigest: sha256:abc\ngenerated: "2026-01-01T00:00:00Z"\n')
        self.artifacts = {'library-1.2.3': {'url': 'https://example.org/charts/library-1.2.3.tgz', 'hash': 'sha256-'+'A'*43+'='}}
        self.data = lock.make_lock(self.root, self.root / 'Chart.lock', self.artifacts)

    def test_valid(self):
        self.assertEqual(lock.problems(self.root, self.root / 'Chart.lock', self.data), [])

    def test_stale(self):
        (self.root / 'Chart.yaml').write_text('changed')
        self.assertTrue(lock.problems(self.root, self.root / 'Chart.lock', self.data))

    def test_tampered(self):
        self.data['artifacts'] = {}
        self.assertIn('contentHash', ' '.join(lock.problems(self.root, self.root / 'Chart.lock', self.data)))

    def test_missing_resealed(self):
        self.data['artifacts'] = {}
        self.assertTrue(lock.problems(self.root, self.root / 'Chart.lock', lock.seal(self.data)))

    def test_bad_versions_cannot_escape(self):
        for name, version in [('../escape', '1.0'), ('lib', '../../escape')]:
            with self.assertRaises(ValueError):
                lock.dependency({'name': name, 'version': version, 'repository': 'https://example.org'})

    def test_no_native_download_metadata_duplication(self):
        artifact = next(iter(self.data['artifacts'].values()))
        self.assertEqual(set(artifact), {'url', 'hash'})

    def test_local_sources_rejected(self):
        with self.assertRaisesRegex(ValueError, 'repository'):
            lock.dependency({'name': 'local', 'version': '1.0.0', 'repository': 'file://../local'})

    def test_alias_repository_rejected_until_resolved(self):
        with self.assertRaises(ValueError):
            lock.dependency({'name': 'lib', 'version': '1.0.0', 'repository': '@alias'})

    def test_json_lock_is_valid_yaml(self):
        (self.root / 'Chart.lock').write_text(json.dumps({'dependencies': [{'name': 'library', 'repository': 'https://example.org/charts', 'version': '1.2.3'}]}))
        self.assertEqual(lock.dependencies(self.root / 'Chart.lock')[0]['key'], 'library-1.2.3')

if __name__ == '__main__':
    unittest.main()
