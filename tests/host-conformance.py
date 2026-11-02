#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native resolution against a real, local Helm repository with two versions."""
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

repository = Path(__file__).resolve().parents[1]
mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
assert mode in ('all', 'relock', 'update', 'external')
cli = Path(subprocess.check_output(['nix', 'build', str(repository), '--no-link', '--print-out-paths'], text=True).strip())

with tempfile.TemporaryDirectory(prefix='helm-conformance-') as temp:
    root = Path(temp)
    env = {**os.environ, 'PATH': str(cli / 'bin') + ':' + os.environ['PATH'], 'HELM_CONFIG_HOME': str(root / 'config'), 'HELM_CACHE_HOME': str(root / 'cache'), 'HELM_DATA_HOME': str(root / 'data')}
    for key in ['HELM_PURIFIER_LOCKFILE', 'HELM_PURIFIER_TOOL_LOCKFILE']:
        env.pop(key, None)

    def command(*args, cwd=root, **kwargs):
        return subprocess.run(args, cwd=cwd, env=env, check=True, **kwargs)

    archive_root = root / 'repository'
    archive_root.mkdir()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(archive_root)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f'http://127.0.0.1:{server.server_port}'
    leaf = root / 'leaf'
    (leaf / 'templates').mkdir(parents=True)
    (leaf / 'templates/message.yaml').write_text('apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: leaf\ndata:\n  leafVersion: "{{ .Chart.Version }}"\n')

    def add_version(version):
        (leaf / 'Chart.yaml').write_text(f'apiVersion: v2\nname: leaf\nversion: {version}\n')
        command('helm', 'package', str(leaf), '--destination', str(archive_root))
        command('helm', 'repo', 'index', str(archive_root), '--url', url)

    project = root / 'project'
    project.mkdir()
    (project / 'Chart.yaml').write_text(f'apiVersion: v2\nname: demo\nversion: 1.0.0\ndependencies:\n- name: leaf\n  version: ">=0.1.0 <0.3.0"\n  repository: {url}\n')
    (project / 'values.yaml').write_text('{}\n')
    native = project / 'Chart.lock'
    sidecar = project / 'helm-purifier.lock.json'
    try:
        add_version('0.1.0')
        command('helm-purifier', 'lock', cwd=project)
        before = native.read_bytes(), sidecar.read_bytes()
        if mode in ('all', 'relock'):
            command('helm-purifier', 'lock', cwd=project)
            command('helm-purifier', 'lock', cwd=project)
            assert before == (native.read_bytes(), sidecar.read_bytes()), 'relock changed bytes'
            sidecar.write_text('not JSON')
            command('helm-purifier', 'lock', cwd=project)
            assert before == (native.read_bytes(), sidecar.read_bytes()), 'malformed companion not repaired'
            print('conformance-relock: byte-identical; malformed companion repaired', flush=True)
        if mode in ('all', 'external'):
            outside = root / 'locks'
            outside.mkdir()
            env['HELM_PURIFIER_LOCKFILE'] = str(outside / 'helm-purifier.lock.json')
            env['HELM_PURIFIER_TOOL_LOCKFILE'] = str(outside / 'Chart.lock')
            command('helm-purifier', 'lock', cwd=project)
            command('helm-purifier', 'prefetch', cwd=project)
            assert before == (native.read_bytes(), sidecar.read_bytes())
            assert before == ((outside / 'Chart.lock').read_bytes(), (outside / 'helm-purifier.lock.json').read_bytes())
            assert (project / 'charts').resolve().is_relative_to('/nix/store')
            assert list((outside / '.helm-purifier').glob('*/runtime'))
            assert '.helm-purifier/' in (project / '.helmignore').read_text()
            rendered = command('helm', 'template', 'purified', '.', cwd=project, capture_output=True, text=True).stdout
            assert 'leafVersion: "0.1.0"' in rendered, rendered
            command('helm', 'lint', '.', cwd=project)
            assert not list(project.glob('*.nix')), 'generated Nix files'
            print('conformance-external: source locks unchanged; prepared chart works through native Helm', flush=True)
            env.pop('HELM_PURIFIER_LOCKFILE')
            env.pop('HELM_PURIFIER_TOOL_LOCKFILE')
        if mode in ('all', 'update'):
            add_version('0.2.0')
            command('helm-purifier', 'lock', cwd=project)
            assert before == (native.read_bytes(), sidecar.read_bytes()), 'lock moved an existing native pin'
            command('helm-purifier', 'update', cwd=project)
            updated = json.loads(sidecar.read_text())
            assert set(updated['artifacts']) == {'leaf-0.2.0'}, updated
            assert native.read_bytes() != before[0]
            assert sidecar.read_bytes() != before[1]
            command('helm-purifier', 'prefetch', cwd=project)
            rendered = command('helm', 'template', 'purified', '.', cwd=project, capture_output=True, text=True).stdout
            assert 'leafVersion: "0.2.0"' in rendered, rendered
            print('conformance-update: native update moved the old pin and prepared the new chart', flush=True)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
