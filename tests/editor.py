# SPDX-License-Identifier: MIT
"""Check real language-server evaluation of the locked fixture imports."""
import json
import os
import select
import subprocess
import time
from pathlib import Path

root = Path.cwd()
server = subprocess.Popen(['helm_ls', 'serve'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def send(message):
    payload = json.dumps({'jsonrpc': '2.0', **message}).encode()
    server.stdin.write(f'Content-Length: {len(payload)}\r\n\r\n'.encode() + payload)
    server.stdin.flush()


pending = b''

def receive():
    global pending
    deadline = time.monotonic() + 30
    while True:
        if b'\r\n\r\n' in pending:
            headers, body = pending.split(b'\r\n\r\n', 1)
            length = int(next(line.split(b':', 1)[1] for line in headers.split(b'\r\n') if line.lower().startswith(b'content-length:')))
            if len(body) >= length:
                pending = body[length:]
                message = json.loads(body[:length])
                if message.get('method') == 'workspace/configuration':
                    settings = {'yamlls': {'enabled': True, 'path': 'yaml-language-server', 'config': {'schemas': {}, 'schemaStore': {'enable': False}, 'schemaDownload': {'enable': False}}}}
                    send({'id': message['id'], 'result': [settings for _ in message['params']['items']]})
                    continue
                if 'method' in message and 'id' in message:
                    send({'id': message['id'], 'result': None})
                    continue
                return message
        remaining = deadline - time.monotonic()
        assert remaining > 0 and select.select([server.stdout], [], [], remaining)[0], 'language server timed out'
        chunk = os.read(server.stdout.fileno(), 65536)
        assert chunk, 'language server exited before responding'
        pending += chunk


try:
    send({'id': 1, 'method': 'initialize', 'params': {'processId': None, 'rootUri': root.as_uri(), 'capabilities': {'workspace': {'configuration': True}}}})
    while True:
        message = receive()
        if message.get('id') == 1:
            assert 'result' in message, message
            break
    send({'method': 'initialized', 'params': {}})
    send({'method': 'textDocument/didOpen', 'params': {'textDocument': {'uri': (root / 'templates/message.yaml').as_uri(), 'languageId': 'helm', 'version': 1, 'text': (root / 'templates/message.yaml').read_text()}}})
    while True:
        message = receive()
        if message.get('method') == 'textDocument/publishDiagnostics':
            errors = [d for d in message['params']['diagnostics'] if d.get('severity', 1) == 1]
            assert not errors, errors
            break
    send({'id': 2, 'method': 'textDocument/hover', 'params': {'textDocument': {'uri': (root / 'templates/message.yaml').as_uri()}, 'position': {'line': 3, 'character': 14}}})
    while True:
        message = receive()
        if message.get('id') == 2:
            assert message.get('result') is not None, message
            break
    # helm-ls exits from its shutdown handler before sending a response.
    send({'id': 3, 'method': 'shutdown', 'params': None})
    server.stdin.close()
    server.wait(timeout=10)
    assert server.returncode == 0
finally:
    if server.poll() is None:
        server.kill()
        server.wait()
print('Helm and YAML language servers processed the prepared chart offline')
