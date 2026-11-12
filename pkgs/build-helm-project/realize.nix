# SPDX-License-Identifier: MIT
{
  project,
  lockFile,
  chartLock,
  target,
}:
let
  pkgs = import (builtins.toPath "@nixpkgs@") { };
  purifier = import (builtins.toPath "@purifier@/nix/lib") { inherit (pkgs) lib; };
  fetchChart = pkgs.callPackage ./fetch-chart.nix { };
  args = {
    src = builtins.toPath project;
    lockFile = builtins.toPath lockFile;
    chartLock = builtins.toPath chartLock;
  };
  lock = (import ../../lib-overlays/default/read-lock.nix { inherit (pkgs) lib; }) args;
in
if target == "charts" then
  pkgs.callPackage ./charts.nix { inherit purifier fetchChart; } { inherit lock; }
else if target == "runtime" then
  pkgs.runCommand "helm-runtime" { } ''ln -s @runtime@ "$out"''
else if target == "release" then
  (pkgs.callPackage ./default.nix { inherit purifier fetchChart; } args).release
else
  throw "helm-purifier: unknown realization target ${target}"
