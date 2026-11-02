# Helm implementation

The expansion report supplies the target, not binding implementation
choices. Helm's native lock digest covers dependency metadata, not the
archive bytes. The companion lock supplies URLs and SHA-256 values.

Native development uses the ordinary charts directory; a wrapper is not
needed. The optional Helm plugin delegates to the Nix package from its
installed Git source. Prefetch roots charts and the full editor/toolchain
closure, and configures native .helmignore to avoid loading those roots.

HTTP(S) repositories and public OCI registries are implemented. The OCI
fetcher negotiates anonymous bearer tokens, validates TLS, drops bearer
headers on redirects across hosts, and verifies the pinned chart bytes
through Nix's fixed-output hash. Set both SSL_CERT_FILE and
NIX_SSL_CERT_FILE in the build script: stdenv sets the latter to a dummy
path, which otherwise overrides OpenSSL's certificate store.

The pure Nix native-lock reader supports Helm's emitted flat YAML and
JSON, with explicit errors for unsupported YAML constructs. It does not
use import-from-derivation. Local and alias repositories and private OCI
credential discovery are explicitly unsupported in this initial version.

Implemented checks cover real HTTP and OCI builds and normalized releases,
lock integrity, external native/companion locks, native offline template
and lint commands, and real Helm/YAML language-server diagnostics and
hover. Native relock/update/external tests use a genuine local HTTP chart
repository and native Helm packaging/resolution, not a fake Helm tool.

All local sandbox checks, native host conformance, output/release rebuild
equality and both-architecture evaluation passed. The OCI fixture skips
upstream test hooks explicitly, since Podinfo generates random test pod
names; its packaged release retains those original test templates.

Published at nix-purifiers/helm-purifier. Initial CI 41383071937 passed
on x86_64-linux and aarch64-linux; Pages 41383071969 passed. Native remote
plugin installation and `helm purifier --help` were verified. Helm 4
requires --verify=false for this Git-source plugin format; README corrected
after testing the actual remote installation.
