# SPDX-License-Identifier: MIT
"""Normalize only archive metadata; retain exactly the native chart payload."""
import gzip
import io
import sys
import tarfile
from pathlib import Path

for source in Path(sys.argv[1]).glob('*.tgz'):
    with tarfile.open(source, 'r:gz') as archive:
        members = archive.getmembers()
        assert all(m.isfile() or m.isdir() for m in members), 'unexpected chart archive member'
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w', format=tarfile.PAX_FORMAT) as output:
            for member in sorted(members, key=lambda m: m.name):
                member.mtime = 1
                member.uid = member.gid = 0
                member.uname = member.gname = ''
                member.pax_headers = {}
                output.addfile(member, archive.extractfile(member) if member.isfile() else None)
        (Path(sys.argv[2]) / source.name).write_bytes(gzip.compress(data.getvalue(), mtime=0))
