# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  runCommand,
  fetchChart,
  kubernetes-helm,
  python3,
  purifier,
}:
{
  src,
  lockFile ? src + "/helm-purifier.lock.json",
  chartLock ? src + "/Chart.lock",
  fetchers ? { },
  releaseName ? "purified",
  valuesFiles ? [ ],
  # Evaluated JSON values from other Nix producers. Each supplied package
  # exports one default document through projections.json.files.default.
  valuesDependencies ? [ ],
  kubeVersion ? null,
  skipTests ? false,
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      "charts"
      ".helm-purifier"
      "result"
      "helm-purifier.lock.json"
      "Chart.lock"
    ]),
}:
let
  selectedValues = purifier.projectInputs {
    dependencies = valuesDependencies;
    formats = [ "json" ];
  };
  projectedValues = map (
    input:
    if input.repository ? files.default then
      input.repository.files.default
    else
      throw "helm-purifier: a values dependency must expose projections.json.files.default"
  ) selectedValues;
  lock = purifier.checkLock (
    (import ./read-lock.nix { inherit lib; }) { inherit src lockFile chartLock; }
  );
  charts = (import ./charts.nix { inherit runCommand fetchChart purifier; }) {
    inherit lock fetchers;
  };
  source = builtins.path {
    path = src;
    name = "helm-project-source";
    filter = srcFilter;
  };
  setup = ''
    export HOME="$TMPDIR/home"
    export HELM_CACHE_HOME="$TMPDIR/cache"
    export HELM_CONFIG_HOME="$TMPDIR/config"
    export HELM_DATA_HOME="$TMPDIR/data"
    mkdir -p "$HOME" "$TMPDIR/project"
    cp -r --no-preserve=mode ${source}/. "$TMPDIR/project/"
    cp ${chartLock} "$TMPDIR/project/Chart.lock"
    cd "$TMPDIR/project"
    ln -s ${charts} charts
  '';
  arguments = lib.escapeShellArgs (
    lib.concatMap (file: [
      "--values"
      file
    ]) (projectedValues ++ valuesFiles)
    ++ lib.optionals (kubeVersion != null) [
      "--kube-version"
      kubeVersion
    ]
  );
  rendered = runCommand "helm-rendered-chart" { nativeBuildInputs = [ kubernetes-helm ]; } ''
    ${setup}
    mkdir -p "$out"
    helm template ${lib.escapeShellArg releaseName} . ${arguments} ${lib.optionalString skipTests "--skip-tests"} > "$out/manifests.yaml"
  '';
  tests = runCommand "helm-chart-tests" { nativeBuildInputs = [ kubernetes-helm ]; } ''
    ${setup}
    helm lint . ${arguments}
    touch "$out"
  '';
  # Helm's package gzip/tar timestamps normally depend on wall-clock time.
  # Repack with fixed metadata while preserving chart contents and modes.
  release =
    runCommand "helm-chart-release"
      {
        nativeBuildInputs = [
          kubernetes-helm
          python3
        ];
      }
      ''
        test -e ${tests}
        ${setup}
        mkdir -p "$TMPDIR/packages" "$out"
        helm package . --destination "$TMPDIR/packages"
        python ${./normalize-chart.py} "$TMPDIR/packages" "$out"
      '';
in
builtins.seq lock {
  packages.chart = rendered;
  inherit tests release;
  fetches = lock.entries;
}
