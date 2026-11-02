# SPDX-License-Identifier: MIT
import io
import json
import unittest
import urllib.error
import urllib.request
from email.message import Message
from unittest.mock import patch, Mock
from helm_purifier import oci

class OciTests(unittest.TestCase):
    def test_bearer_challenge(self):
        headers = Message()
        headers['WWW-Authenticate'] = 'Bearer realm="https://auth.example/token",service="registry.example",scope="repository:charts/lib:pull"'
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError('https://registry.example/v2/charts/lib', 401, 'authentication', headers, None), io.BytesIO(b'{"token":"ephemeral-read-token"}'), io.BytesIO(b'chart')]
        with patch('urllib.request.build_opener', return_value=opener):
            with oci.request('https://registry.example/v2/charts/lib') as result:
                self.assertEqual(result.read(), b'chart')
        self.assertIn('scope=repository%3Acharts%2Flib%3Apull', opener.open.call_args_list[1].args[0])
        self.assertEqual(opener.open.call_args_list[2].args[0].get_header('Authorization'), 'Bearer ephemeral-read-token')

    def test_insecure_token_endpoint_rejected(self):
        headers = Message()
        headers['WWW-Authenticate'] = 'Bearer realm="http://auth.example/token"'
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('https://registry.example', 401, '', headers, None)
        with patch('urllib.request.build_opener', return_value=opener), self.assertRaisesRegex(ValueError, 'endpoint'):
            oci.request('https://registry.example')

    def test_redirect_drops_authorization_across_hosts(self):
        request = urllib.request.Request('https://registry.example/blob', headers={'Authorization': 'Bearer token'})
        redirect = oci.SafeRedirect().redirect_request(request, None, 302, '', {}, 'https://storage.example/blob')
        self.assertIsNone(redirect.get_header('Authorization'))

    def test_manifest_locks_blob_digest_not_tag(self):
        payload = {'layers': [{'mediaType': 'application/vnd.cncf.helm.chart.content.v1.tar+gzip', 'digest': 'sha256:' + 'a'*64}]}
        with patch.object(oci, 'request', return_value=io.BytesIO(json.dumps(payload).encode())):
            url, digest = oci.chart_layer('oci://registry.example/charts', 'lib', '1.0.0+build')
        self.assertEqual(url, 'oci+https://registry.example/v2/charts/lib/blobs/sha256:' + 'a'*64)
        self.assertEqual(digest, 'a'*64)

    def test_multiple_layers_rejected(self):
        layer = {'mediaType': 'application/vnd.cncf.helm.chart.content.v1.tar+gzip', 'digest': 'sha256:' + 'a'*64}
        with patch.object(oci, 'request', return_value=io.BytesIO(json.dumps({'layers': [layer, layer]}).encode())), self.assertRaises(ValueError):
            oci.chart_layer('oci://registry.example/charts', 'lib', '1.0')

if __name__ == '__main__':
    unittest.main()
