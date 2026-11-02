# SPDX-License-Identifier: MIT
"""Anonymous OCI bearer authentication; credentials never enter a lock."""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        original = urllib.parse.urlsplit(request.full_url)
        target = urllib.parse.urlsplit(newurl)
        if original.scheme == 'https' and target.scheme != 'https':
            raise ValueError('refusing an HTTPS-to-HTTP registry redirect')
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is not None and (original.scheme, original.netloc) != (target.scheme, target.netloc):
            redirected.remove_header('Authorization')
        return redirected


def request(url, accept='application/octet-stream'):
    opener = urllib.request.build_opener(SafeRedirect())
    headers = {'Accept': accept, 'User-Agent': 'helm-purifier/0.1.0'}
    try:
        return opener.open(urllib.request.Request(url, headers=headers), timeout=60)
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
        challenge = error.headers.get('WWW-Authenticate', '')
        error.close()
    if not challenge.lower().startswith('bearer '):
        raise ValueError('registry requires credentials; configure an authenticated fetcher')
    parameters = dict(re.findall(r'([a-zA-Z_]+)="([^"\r\n]*)"', challenge))
    realm = parameters.pop('realm', '')
    parsed = urllib.parse.urlsplit(realm)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('registry returned an unsupported bearer token endpoint')
    token_url = realm + ('&' if parsed.query else '?') + urllib.parse.urlencode(parameters)
    with opener.open(token_url, timeout=60) as response:
        payload = json.load(response)
    token = payload.get('token') or payload.get('access_token')
    if not isinstance(token, str) or not token or '\n' in token or '\r' in token:
        raise ValueError('registry returned an invalid bearer token')
    headers['Authorization'] = 'Bearer ' + token
    return opener.open(urllib.request.Request(url, headers=headers), timeout=60)


def chart_layer(repository, name, version):
    parsed = urllib.parse.urlsplit(repository)
    if parsed.scheme != 'oci' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('invalid OCI repository URL')
    path = parsed.path.strip('/')
    if any(part in ('', '.', '..') for part in (path + '/' + name).split('/')):
        raise ValueError('unsafe OCI repository path')
    base = f'https://{parsed.netloc}/v2/{path}/{name}'
    # Helm follows OCI's replacement of SemVer build metadata '+' with '_'.
    url = base + '/manifests/' + urllib.parse.quote(version.replace('+', '_'), safe='._-')
    with request(url, 'application/vnd.oci.image.manifest.v1+json') as response:
        manifest = json.load(response)
    layers = [layer for layer in manifest.get('layers', []) if layer.get('mediaType') == 'application/vnd.cncf.helm.chart.content.v1.tar+gzip']
    if len(layers) != 1 or not re.fullmatch('sha256:[0-9a-f]{64}', layers[0].get('digest', '')):
        raise ValueError('OCI manifest must contain exactly one SHA-256 Helm chart layer')
    digest = layers[0]['digest']
    return 'oci+https' + base.removeprefix('https') + '/blobs/' + digest, digest.removeprefix('sha256:')


if __name__ == '__main__':
    url = sys.argv[1].removeprefix('oci+')
    with request(url) as response, Path(sys.argv[2]).open('wb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
