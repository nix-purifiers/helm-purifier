# SPDX-License-Identifier: MIT
{
  pkgs,
  purifier,
  buildHelmProject,
}:
let
  src = ./fixtures/json-values;
  body = {
    version = 1;
    inputs = {
      "Chart.yaml" = builtins.hashFile "sha256" (src + "/Chart.yaml");
      "Chart.lock" = builtins.hashFile "sha256" (src + "/Chart.lock");
    };
    artifacts = { };
  };
  lockFile = pkgs.writeText "helm-purifier.lock.json" (
    builtins.toJSON (
      body
      // {
        contentHash = builtins.hashString "sha256" (builtins.toJSON body);
      }
    )
  );
  source = pkgs.writeTextDir "values.json" ''{"answer":42}'';
  values = source // {
    projections = purifier.dataProjections {
      producer = source;
      files.default = "values.json";
      inherit (pkgs) runCommand python3;
    };
  };
  built = buildHelmProject {
    inherit src lockFile;
    valuesDependencies = [ values ];
  };
  rejected = builtins.tryEval (
    (buildHelmProject {
      inherit src lockFile;
      valuesDependencies = [ source ];
    }).packages.chart.drvPath
  );
in
assert built.fetches == [ ];
assert !rejected.success;
pkgs.runCommand "helm-json-values-dependency" { } ''
  grep -F 'answer: "42"' ${built.packages.chart}/manifests.yaml
  test -e ${built.tests}
  touch $out
''
