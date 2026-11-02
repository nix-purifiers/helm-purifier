#!/usr/bin/env sh
# SPDX-License-Identifier: MIT
set -eu
cd "$(dirname "$0")/.."
system=$(nix eval --impure --raw --expr builtins.currentSystem)
nix build ".#checks.$system.fixture" ".#checks.$system.release" ".#checks.$system.oci-fixture" ".#checks.$system.oci-release" --no-link
nix build ".#checks.$system.fixture" ".#checks.$system.release" ".#checks.$system.oci-fixture" ".#checks.$system.oci-release" --no-link --rebuild
