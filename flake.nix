# SPDX-License-Identifier: MIT
{
  description = "Locked, Nix-resolved dependencies for Helm";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      shared = lib: import (purifier + "/nix/lib") { inherit lib; };
      overlay = final: prev: {
        helm-purifier = final.lib.makeScope final.newScope (scope: {
          cli = scope.callPackage ./pkgs/cli/default.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          fetchChart = scope.callPackage ./pkgs/build-helm-project/fetch-chart.nix { };
          buildHelmProject = scope.callPackage ./pkgs/build-helm-project/default.nix {
            purifier = shared final.lib;
          };
        });
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      lib.helm-purifier = (nixpkgs.lib.extend (import ./lib-overlays/default)).helm-purifier;
      packages = forAll (system: {
        default = (pkgsFor system).helm-purifier.cli;
        cli = self.packages.${system}.default;
      });
      apps = forAll (system: {
        default = {
          type = "app";
          meta.description = "Lock and prefetch Helm dependencies";
          program = "${self.packages.${system}.default}/bin/helm-purifier";
        };
      });
      devShells = forAll (system: {
        default = (pkgsFor system).mkShell {
          packages = [
            self.packages.${system}.default
            ((pkgsFor system).python3.withPackages (p: [ p.pyyaml ]))
          ];
        };
      });
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
      checks = forAll (
        system:
        import ./tests {
          pkgs = pkgsFor system;
          inherit self;
        }
      );
    };
}
