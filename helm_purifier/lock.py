# SPDX-License-Identifier: MIT
"""Read native Helm coordinates; store missing archive URLs and hashes."""
import hashlib
import json
import re
import yaml
from pathlib import Path
from urllib.parse import urlsplit

ADVICE = 'run helm-purifier lock (with --lockfile/--tool-lockfile for external locks)'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(data):
    data = {k: v for k, v in data.items() if k != 'contentHash'}
    return {**data, 'contentHash': digest(data)}


def load_yaml(path):
    try:
        value = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f'cannot read {path}: {error}') from error
    if not isinstance(value, dict):
        raise ValueError(f'{path} must contain a mapping')
    return value


def dependency(dep):
    if not isinstance(dep, dict):
        raise ValueError('invalid Chart.lock dependency')
    name, version, repository = dep.get('name'), dep.get('version'), dep.get('repository')
    if not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', name) or '..' in name:
        raise ValueError('unsafe chart name')
    if not isinstance(version, str) or not re.fullmatch('[0-9][A-Za-z0-9_.+-]*', version) or '..' in version:
        raise ValueError('unsafe chart version')
    parsed = urlsplit(repository) if isinstance(repository, str) else None
    if parsed is None or parsed.scheme not in ('https', 'http', 'oci') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('unsupported repository: use an HTTP(S) chart repository URL; local and alias repositories are not yet supported')
    return {'key': f'{name}-{version}', 'name': name, 'version': version, 'repository': repository}


def dependencies(path):
    native = load_yaml(path)
    deps = native.get('dependencies') or []
    if not isinstance(deps, list):
        raise ValueError('Chart.lock dependencies must be a list')
    result = [dependency(d) for d in deps]
    if len({d['key'] for d in result}) != len(result):
        raise ValueError('duplicate chart dependency')
    return result


def make_lock(root, native_path, artifacts):
    return seal({'version': 1, 'inputs': {'Chart.yaml': file_hash(root / 'Chart.yaml'), 'Chart.lock': file_hash(native_path)}, 'artifacts': artifacts})


def problems(root, native_path, data):
    try:
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('unsupported purifier lock format')
        if data.get('contentHash') != digest({k: v for k, v in data.items() if k != 'contentHash'}):
            raise ValueError('contentHash mismatch')
        for name, path in [('Chart.yaml', root / 'Chart.yaml'), ('Chart.lock', native_path)]:
            if data.get('inputs', {}).get(name) != file_hash(path):
                raise ValueError(f'{name} changed after locking')
        deps = dependencies(native_path)
        artifacts = data.get('artifacts')
        if not isinstance(artifacts, dict) or set(artifacts) != {d['key'] for d in deps}:
            raise ValueError('missing or extra chart artifacts')
        for key, artifact in artifacts.items():
            if not isinstance(artifact, dict) or not isinstance(artifact.get('hash'), str) or not re.fullmatch(r'sha256-[A-Za-z0-9+/]{43}=', artifact['hash']):
                raise ValueError(f'invalid chart archive hash: {key}')
            url = urlsplit(artifact['url'])
            if url.scheme not in ('https', 'http', 'oci+https') or not url.hostname or url.username or url.password or url.fragment:
                raise ValueError(f'invalid chart archive URL: {key}')
        return []
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        return [f'helm-purifier: {error}; {ADVICE}']
