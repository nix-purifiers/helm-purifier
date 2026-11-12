# SPDX-License-Identifier: MIT
# Registry tokens are ephemeral transport state; Nix verifies the chart bytes.
{
  lib,
  fetchurl,
  stdenvNoCC,
  python3,
  cacert,
}:
args:
let
  url = args.url or (builtins.head args.urls);
in
if !(lib.hasPrefix "oci+https://" url) then
  fetchurl args
else
  stdenvNoCC.mkDerivation {
    inherit (args) name;
    dontUnpack = true;
    nativeBuildInputs = [ python3 ];
    SSL_CERT_FILE = "${cacert}/etc/ssl/certs/ca-bundle.crt";
    impureEnvVars = lib.fetchers.proxyImpureEnvVars;
    outputHash = args.hash;
    outputHashMode = "flat";
    outputHashAlgo = "sha256";
    preferLocalBuild = true;
    buildCommand = ''
      export SSL_CERT_FILE=${cacert}/etc/ssl/certs/ca-bundle.crt
      if [ -f "''${NIX_SSL_CERT_FILE:-}" ]; then export SSL_CERT_FILE="$NIX_SSL_CERT_FILE"; fi
      export NIX_SSL_CERT_FILE="$SSL_CERT_FILE"
      python ${../../helm_purifier/oci.py} ${lib.escapeShellArg url} "$out"
    '';
  }
