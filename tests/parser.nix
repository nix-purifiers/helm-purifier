# SPDX-License-Identifier: MIT
{ lib }:
let
  parse = import ../lib-overlays/default/chart-lock.nix { inherit lib; };
  source = builtins.toFile "Chart.lock" ''
    dependencies:
    - name: "example"
      version: '1.2.3'
      repository: https://charts.example.org
    digest: sha256:abc123
    generated: "2026-01-01T00:00:00Z"
  '';
  expected = {
    dependencies = [
      {
        name = "example";
        version = "1.2.3";
        repository = "https://charts.example.org";
      }
    ];
  };
  malformed = builtins.toFile "Chart.lock" "dependencies:\n- name: ../escape\n unexpected\n";
  bad = builtins.tryEval (builtins.deepSeq (parse malformed) true);
in
assert parse source == expected;
assert parse (builtins.toFile "Chart.lock" (builtins.toJSON expected)) == expected;
assert parse (builtins.toFile "Chart.lock" "dependencies: []\n") == { dependencies = [ ]; };
assert !bad.success;
true
