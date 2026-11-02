# helm-purifier

Locked, Nix-resolved dependencies for Helm.

## Quickstart

From a chart with `Chart.yaml`:

```sh
nix shell 'github:nix-purifiers/helm-purifier'
helm-purifier lock
helm-purifier prefetch
helm template development .
helm lint .
```

`lock` uses Helm to resolve dependencies. `prefetch` realizes the locked
chart archives with Nix and prepares `charts/`. Rendering, linting and
packaging use ordinary Helm in your working tree. No project Nix files or
wrapper activation are required.

Prefetch adds ignore rules for `.helm-purifier/` and the companion lock to
`.helmignore`, preserving existing rules. This keeps local GC roots and
tools out of packaged charts. Ignore `charts/` and `.helm-purifier/` in Git.
An existing charts directory is never deleted automatically; move it aside
before the first prefetch. Persistent installation is optional.

For an existing Helm installation, the same commands are available as a
native plugin:

```sh
helm plugin install --verify=false \
  https://github.com/nix-purifiers/helm-purifier
helm purifier lock
helm purifier prefetch
helm template development .
```

Helm 4 requires `--verify=false` for Git-source plugins; artifact signature
verification is unavailable for that plugin format.
The plugin uses its installed source and pinned Nix inputs. Nix must be
available. No separate Helm package registry is required to install it.

## Development loop

```sh
helm template development .
helm lint .
helm-purifier update
helm-purifier prefetch
```

Commit `Chart.lock`, `helm-purifier.lock.json` and `.helmignore`. Relocking
keeps usable native pins. After changing dependency requirements, run
`helm-purifier lock` to reconcile the native lock and companion metadata.
`update` uses `helm dependency update` to refresh both locks together.
Helm has no named dependency-update operation, so named updates fail with
an explanation.

External locks work without replacing a native lock in the source:

```sh
lockdir="$PWD/../locks"
export HELM_PURIFIER_LOCKFILE="$lockdir/helm-purifier.lock.json"
export HELM_PURIFIER_TOOL_LOCKFILE="$lockdir/Chart.lock"
helm-purifier lock
helm-purifier prefetch
```

Global `--lockfile` and `--tool-lockfile` flags override the environment;
put them before the subcommand. A missing external native lock is seeded
from the source's native lock.

## Working offline

Run `helm-purifier prefetch` while online. It realizes and roots the chart
archives, Helm, Helm Language Server and its YAML worker. Then rendering,
linting and packaging use those local dependencies:

```sh
helm template development .
helm lint .
helm package .
```

`helm dependency update`, pulling a new chart, and cluster operations can
still require the network. Use the purifier's lock/update and prefetch
commands to prepare dependency changes. Stale or invalid locks fail with
the command needed to repair them.

## Editor

Start the supplied language server from the chart root:

```sh
helm_ls serve
```

It uses prepared dependency charts for template and values completion.
The package includes `yaml-language-server`. For offline YAML features,
configure its settings through Helm Language Server:

```json
{
  "helm-ls": {
    "yamlls": {
      "path": "yaml-language-server",
      "config": {
        "schemas": {},
        "schemaStore": { "enable": false },
        "schemaDownload": { "enable": false }
      }
    }
  }
}
```

You can associate locally provided schemas instead. This avoids asking the
editor to download remote Kubernetes or SchemaStore schemas.

## Troubleshooting

- **Stale or malformed lock:** run `helm-purifier lock`.
- **Existing charts directory:** move it aside before prefetch. Store
  symlinks created by prefetch are refreshed automatically.
- **Index checksum mismatch:** locking fails rather than trusting changed
  chart bytes. Check the repository's index and release archive.
- **Repository alias:** use the HTTP(S) or OCI URL in `Chart.yaml`.
- **Custom native YAML:** the Nix reader accepts the flat `Chart.lock`
  format Helm generates, and JSON-form locks. Advanced YAML constructs
  such as anchors are rejected explicitly.

## Supported language repositories

HTTP(S) chart repositories and public OCI registries, including GHCR.
Each chart archive is a separately hashed shared-library file entry.
OCI resolution records the chart layer's blob digest, and Nix fetches it
using anonymous bearer authentication. Tokens are neither locked nor
stored. Repository aliases, local `file://` dependencies and private OCI
credential discovery are not currently supported by the lock command.

Nix builders accept `fetchers.fetchurl` for company mirrors or credential
handling. Ordinary archive and OCI entries use that same override hook.
The default OCI fetcher verifies TLS and the locked SHA-256. Toolchain
versions come from the pinned nixpkgs; the overlay also accepts a compatible
supplied package set with Helm 4, Python 3.11+, Helm LS and its YAML worker.

## Examples

[`examples/hello`](examples/hello) depends on a chart from the Prometheus
community repository. [`examples/oci`](examples/oci) depends on Podinfo
from GHCR. Both work without project Nix files:

```sh
cd examples/hello
helm-purifier prefetch
helm template development .
helm lint .
```

### Building the chart with Nix

Add a project flake or keep the packaging definition in another repository:

```nix
let
  pkgs = import nixpkgs {
    inherit system;
    overlays = [ helm-purifier.overlays.default ];
  };
  project = pkgs.helm-purifier.buildHelmProject {
    src = ./.;
    releaseName = "development";
  };
in project.packages.chart
```

The builder returns `packages.chart` (rendered manifests), `tests` (Helm
lint), `release` (a normalized native chart archive), and `fetches`.
`lockFile` and `chartLock` accept external paths, replacing source locks.
`valuesFiles` selects chart-relative value files; `kubeVersion` fixes Helm's
target Kubernetes capabilities. `skipTests = true` omits Helm test hooks;
the Podinfo fixture uses this because its test pod names are randomized.
`srcFilter` customizes source filtering,
and `fetchers` passes unchanged to the shared library. Output names are
known at evaluation time without IFD.

Use `buildHelmProject.override` or `helm-purifier.overrideScope` to replace
build tools. The overlay can also use ambient `<nixpkgs>`.
`lib.helm-purifier.readLock` exposes the shared in-memory lock shape.

Publish the Nix-built chart to an OCI registry:

```sh
helm-purifier publish \
  oci://ghcr.io/OWNER/charts
```

This uses Helm's normal registry credentials. Rendering and packaging do
not deploy anything to a Kubernetes cluster.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).

[Helm](https://helm.sh/),
[Helm Language Server](https://github.com/mrjosh/helm-ls),
[Prometheus community charts](https://github.com/prometheus-community/helm-charts),
and [Podinfo](https://github.com/stefanprodan/podinfo).
Fetches use the shared [purifier library](https://github.com/nix-purifiers/purifier).
