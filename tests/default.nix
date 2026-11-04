# SPDX-License-Identifier: MIT
{ pkgs, self }:
let
  python = pkgs.python3.withPackages (p: [ p.pyyaml ]);
  fixture = ../examples/hello;
  project = pkgs.helm-purifier.buildHelmProject { src = fixture; };
  oci = pkgs.helm-purifier.buildHelmProject {
    src = ../examples/oci;
    skipTests = true;
  };
  lock = self.lib.helm-purifier.readLock { src = fixture; };
  purifier = import (self.inputs.purifier + "/nix/lib") { inherit (pkgs) lib; };
  charts = pkgs.helm-purifier.callPackage ../nix/charts.nix { inherit purifier; } { inherit lock; };
  mkErrorCheck =
    case:
    pkgs.runCommand "helm-conformance-${case}"
      {
        nativeBuildInputs = [
          python
          pkgs.nix
        ];
        SOURCE = self;
        NIXPKGS_LIB = "${pkgs.path}/lib";
        PURIFIER = self.inputs.purifier;
        PYTHONPATH = self;
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        python ${./eval-errors.py} ${case}
        touch "$out"
      '';
  externalSource = builtins.path {
    path = fixture;
    name = "helm-external-source";
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        "Chart.lock"
        "helm-purifier.lock.json"
        "charts"
        ".helm-purifier"
      ]);
  };
  external = pkgs.helm-purifier.buildHelmProject {
    src = externalSource;
    lockFile = fixture + "/helm-purifier.lock.json";
    chartLock = fixture + "/Chart.lock";
  };
in
{
  json-values = import ./json-values.nix {
    inherit pkgs purifier;
    inherit (pkgs.helm-purifier) buildHelmProject;
  };
  unit =
    assert import ./parser.nix { inherit (pkgs) lib; };
    pkgs.runCommand "helm-purifier-unit" { nativeBuildInputs = [ python ]; } ''
      cp -r ${self} source
      chmod -R u+w source
      cd source
      python -m unittest discover -s tests -v
      touch "$out"
    '';
  formatting =
    pkgs.runCommand "helm-formatting"
      {
        nativeBuildInputs = [
          pkgs.nixfmt
          pkgs.findutils
        ];
      }
      ''
        find ${self} -name '*.nix' -print0 | xargs -0 nixfmt --check
        touch "$out"
      '';
  conformance-stale = mkErrorCheck "stale";
  conformance-tampered = mkErrorCheck "tampered";
  conformance-missing = mkErrorCheck "missing";
  conformance-malformed = mkErrorCheck "malformed";
  conformance-external = pkgs.runCommand "helm-conformance-external" { } ''
    test ! -e ${externalSource}/Chart.lock
    test ! -e ${externalSource}/helm-purifier.lock.json
    cmp ${project.packages.chart}/manifests.yaml ${external.packages.chart}/manifests.yaml
    touch "$out"
  '';
  fixture = project.packages.chart;
  fixture-tests = project.tests;
  release = project.release;
  oci-fixture = oci.packages.chart;
  oci-tests = oci.tests;
  oci-release = oci.release;
  conformance-offline =
    pkgs.runCommand "helm-conformance-offline"
      {
        nativeBuildInputs = [
          pkgs.helm-purifier.cli
          python
        ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        cp -r ${fixture} chart
        chmod -R u+w chart
        cd chart
        ln -s ${charts} charts
        helm template purified . > actual.yaml
        cmp actual.yaml ${project.packages.chart}/manifests.yaml
        helm lint .
        python ${./editor.py}
        touch "$out"
      '';
}
