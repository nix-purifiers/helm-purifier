# SPDX-License-Identifier: MIT
"""Prepare Helm's native charts directory from individually locked archives."""
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urljoin
import yaml
from . import lock, oci


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f'cannot read {path}: {error}; {lock.ADVICE}') from error


def checked(root, sidecar, native):
    errors = lock.problems(root, native, read_json(sidecar))
    if errors:
        raise ValueError('\n'.join(errors))


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(data)
        temporary = Path(stream.name)
    temporary.replace(path)


def realize(root, sidecar, native, target):
    state = sidecar.parent / '.helm-purifier' / lock.digest(str(root))[:12]
    state.mkdir(parents=True, exist_ok=True)
    profile = state / target
    run(['nix', 'build', '--impure', '--file', os.environ['HELM_PURIFIER_REALIZE'], '--argstr', 'project', str(root), '--argstr', 'lockFile', str(sidecar), '--argstr', 'chartLock', str(native), '--argstr', 'target', target, '--out-link', str(profile)])
    return profile.resolve()


def prepare(root, sidecar, native):
    checked(root, sidecar, native)
    destination = root / 'charts'
    if destination.is_symlink():
        if not destination.resolve().is_relative_to('/nix/store'):
            raise ValueError('charts is a user-owned symlink; move it aside before prefetch')
    elif destination.exists():
        raise ValueError('charts already exists; move it aside before prefetch (it is never deleted automatically)')
    charts = realize(root, sidecar, native, 'charts')
    realize(root, sidecar, native, 'runtime')
    if destination.is_symlink():
        destination.unlink()
    destination.symlink_to(charts, target_is_directory=True)
    # Helm recursively loads the chart directory, so GC roots must be ignored
    # before the native loader follows their toolchain symlinks.
    ignore_file = root / '.helmignore'
    content = ignore_file.read_text() if ignore_file.exists() else ''
    missing = [pattern for pattern in ['.helm-purifier/', 'helm-purifier.lock.json'] if pattern not in content.splitlines()]
    if missing:
        write_bytes(ignore_file, (content.rstrip('\n') + '\n# Local purifier state\n' + '\n'.join(missing) + '\n').encode())


def do_lock(args, root, sidecar, native, update=False):
    if update and args.packages:
        raise ValueError('Helm updates dependencies together; named updates are not supported by helm dependency update')
    # Fail unsupported sources before running native code or mutating any lock.
    manifest = lock.load_yaml(root / 'Chart.yaml')
    for dep in manifest.get('dependencies') or []:
        source = dep.get('repository', '')
        if not isinstance(source, str) or not source.startswith(('http://', 'https://', 'oci://')):
            raise ValueError('only HTTP(S) and OCI chart repositories are currently supported; resolve repository aliases to URLs in Chart.yaml')
    with tempfile.TemporaryDirectory(prefix='helm-purifier-lock-') as temp:
        stage = Path(temp) / 'project'
        shutil.copytree(root, stage, copy_function=shutil.copyfile, ignore=shutil.ignore_patterns('.git', 'charts', '.helm-purifier', 'result*'))
        seed = native if native.exists() else root / 'Chart.lock'
        stage_native = stage / 'Chart.lock'
        try:
            seed_data = lock.load_yaml(seed) if seed.exists() else None
        except ValueError:
            seed_data = None
        if seed_data is not None:
            shutil.copyfile(seed, stage_native)
        elif stage_native.exists():
            stage_native.unlink()
        env = {**os.environ, 'HELM_CACHE_HOME': str(Path(temp) / 'cache')}
        helm = os.environ.get('HELM_PURIFIER_HELM', 'helm')
        # Native `dependency build` needs registered repositories even for
        # URL dependencies. Keep that registration/cache out of user state.
        config_home = Path(os.environ.get('HELM_CONFIG_HOME', Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'helm'))
        original_config = Path(os.environ.get('HELM_REPOSITORY_CONFIG', config_home / 'repositories.yaml'))
        repositories = lock.load_yaml(original_config).get('repositories', []) if original_config.exists() else []
        isolated_config = Path(temp) / 'config' / 'repositories.yaml'
        isolated_config.parent.mkdir()
        if original_config.exists():
            shutil.copyfile(original_config, isolated_config)
        env['HELM_CONFIG_HOME'] = str(isolated_config.parent)
        env['HELM_REPOSITORY_CONFIG'] = str(isolated_config)
        for dep in manifest.get('dependencies') or []:
            source = dep['repository']
            if source.startswith('oci://') or any(r.get('url', '').rstrip('/') == source.rstrip('/') for r in repositories):
                continue
            name = 'purifier-' + hashlib.sha256(source.encode()).hexdigest()[:24]
            run([helm, 'repo', 'add', name, source], env=env)
            repositories.append({'name': name, 'url': source})
        operation = 'update' if update or seed_data is None else 'build'
        resolved = subprocess.run([helm, 'dependency', operation, str(stage)], env=env, text=True, capture_output=True)
        sys.stdout.write(resolved.stdout)
        sys.stderr.write(resolved.stderr)
        if resolved.returncode and operation == 'build' and 'out of sync' in resolved.stderr:
            run([helm, 'dependency', 'update', str(stage)], env=env)
        else:
            resolved.check_returncode()
        if not stage_native.exists():
            # Helm writes no native lock for an empty graph; JSON is valid YAML.
            stage_native.write_text('{"dependencies": []}\n')
        deps = lock.dependencies(stage_native)
        indexes = {}
        artifacts = {}
        for dep in deps:
            if dep['repository'].startswith('oci://'):
                url, expected = oci.chart_layer(dep['repository'], dep['name'], dep['version'])
            else:
                repository = dep['repository'].rstrip('/') + '/'
                if repository not in indexes:
                    request = urllib.request.Request(urljoin(repository, 'index.yaml'), headers={'User-Agent': 'helm-purifier/0.1.0'})
                    credentials = next((r for r in repositories if r.get('url', '').rstrip('/') == repository.rstrip('/')), {})
                    if credentials.get('username'):
                        basic = (credentials['username'] + ':' + credentials.get('password', '')).encode()
                        request.add_header('Authorization', 'Basic ' + base64.b64encode(basic).decode())
                    opener = urllib.request.build_opener(oci.SafeRedirect())
                    with opener.open(request, timeout=60) as response:
                        indexes[repository] = yaml.safe_load(response.read())
                records = indexes[repository].get('entries', {}).get(dep['name'], [])
                candidates = [r for r in records if str(r.get('version')) == dep['version']]
                if not candidates or not candidates[0].get('urls'):
                    raise ValueError(f'{dep["key"]}: archive URL is missing from repository index')
                record = candidates[0]
                url = urljoin(repository, record['urls'][0])
                expected = record.get('digest', '').removeprefix('sha256:')
            archive = stage / 'charts' / (dep['key'] + '.tgz')
            digest = hashlib.sha256(archive.read_bytes()).digest()
            if expected and expected != digest.hex():
                raise ValueError(f'{dep["key"]}: downloaded chart differs from index SHA-256')
            artifacts[dep['key']] = {'url': url, 'hash': 'sha256-' + base64.b64encode(digest).decode()}
        # Preserve the exact source native lock bytes for unchanged resolution.
        data_bytes = stage_native.read_bytes()
        if seed_data is not None and seed_data == lock.load_yaml(stage_native):
            data_bytes = seed.read_bytes()
        candidate = Path(temp) / 'Chart.lock'
        candidate.write_bytes(data_bytes)
        data = lock.make_lock(root, candidate, artifacts)
        errors = lock.problems(root, candidate, data)
        if errors:
            raise ValueError('\n'.join(errors))
        if not native.exists() or native.read_bytes() != data_bytes:
            write_bytes(native, data_bytes)
        write_bytes(sidecar, (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode())
    print(f'Locked {len(artifacts)} charts in {sidecar}')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='helm-purifier')
    parser.add_argument('--lockfile')
    parser.add_argument('--tool-lockfile')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('lock').set_defaults(packages=[])
    sub.add_parser('update').add_argument('packages', nargs='*')
    sub.add_parser('prefetch')
    publish = sub.add_parser('publish')
    publish.add_argument('repository', help='OCI repository, e.g. oci://ghcr.io/OWNER/charts')
    args = parser.parse_args(argv)
    root = Path.cwd()
    sidecar = Path(args.lockfile or os.environ.get('HELM_PURIFIER_LOCKFILE', root / 'helm-purifier.lock.json')).resolve()
    native = Path(args.tool_lockfile or os.environ.get('HELM_PURIFIER_TOOL_LOCKFILE', root / 'Chart.lock')).resolve()
    try:
        if args.command in ('lock', 'update'):
            do_lock(args, root, sidecar, native, args.command == 'update')
        elif args.command == 'prefetch':
            prepare(root, sidecar, native)
        else:
            if not args.repository.startswith('oci://'):
                raise ValueError('publish requires an oci:// repository')
            checked(root, sidecar, native)
            release = realize(root, sidecar, native, 'release')
            packages = sorted(release.glob('*.tgz'))
            if len(packages) != 1:
                raise ValueError('release must contain exactly one packaged chart')
            run([os.environ.get('HELM_PURIFIER_HELM', 'helm'), 'push', str(packages[0]), args.repository])
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError) as error:
        print(f'helm-purifier: {error}', file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode > 0 else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
