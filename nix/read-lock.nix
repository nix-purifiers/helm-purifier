# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/helm-purifier.lock.json",
  chartLock ? src + "/Chart.lock",
}:
let
  problem =
    message:
    "helm-purifier: ${message}; run helm-purifier lock (use --lockfile and --tool-lockfile for external locks)";
  exists = builtins.all builtins.pathExists [
    lockFile
    chartLock
    (src + "/Chart.yaml")
  ];
  data =
    if exists then
      builtins.addErrorContext (problem "cannot parse purifier lock") (
        builtins.fromJSON (builtins.readFile lockFile)
      )
    else
      { };
  native = if exists then (import ./chart-lock.nix { inherit lib; }) chartLock else { };
  decoded = map (dep: dep // { key = "${dep.name}-${dep.version}"; }) (native.dependencies or [ ]);
  keys = map (dep: dep.key) decoded;
  valid =
    dep:
    builtins.isAttrs dep
    && builtins.isString (dep.name or null)
    && builtins.match "[A-Za-z0-9][A-Za-z0-9_.-]*" dep.name != null
    && !(lib.hasInfix ".." dep.name)
    && builtins.isString (dep.version or null)
    && builtins.match "[0-9][A-Za-z0-9_.+-]*" dep.version != null
    && !(lib.hasInfix ".." dep.version)
    && builtins.isString (dep.repository or null)
    && builtins.match "(https?|oci)://[^/@?#]+[^?#]*" dep.repository != null;
  artifacts = data.artifacts or { };
  problems = map problem (
    if !exists then
      [ "missing lockfile or Chart.yaml" ]
    else if !builtins.isAttrs data || (data.version or null) != 1 then
      [ "unsupported purifier lock format" ]
    else if
      (data.contentHash or null)
      != builtins.hashString "sha256" (builtins.toJSON (removeAttrs data [ "contentHash" ]))
    then
      [ "contentHash mismatch" ]
    else if !builtins.isAttrs (data.inputs or null) then
      [ "missing input fingerprints" ]
    else if (data.inputs."Chart.yaml" or null) != builtins.hashFile "sha256" (src + "/Chart.yaml") then
      [ "Chart.yaml changed after locking" ]
    else if (data.inputs."Chart.lock" or null) != builtins.hashFile "sha256" chartLock then
      [ "Chart.lock changed after locking" ]
    else if
      !builtins.isAttrs native
      || !builtins.isList (native.dependencies or null)
      || !builtins.all valid native.dependencies
    then
      [ "unsupported native chart dependencies" ]
    else if builtins.length (lib.unique keys) != builtins.length keys then
      [ "duplicate chart dependencies" ]
    else if
      !builtins.isAttrs artifacts || builtins.attrNames artifacts != builtins.sort builtins.lessThan keys
    then
      [ "missing or extra chart artifacts" ]
    else if
      !(builtins.all (
        a:
        builtins.isAttrs a
        && builtins.isString (a.hash or null)
        && builtins.match "sha256-[A-Za-z0-9+/]{43}=" a.hash != null
        && builtins.isString (a.url or null)
        && builtins.match "(https?|oci\\+https)://[^/@#]+[^#]*" a.url != null
      ) (builtins.attrValues artifacts))
    then
      [ "invalid chart archive URL or hash" ]
    else
      [ ]
  );
in
{
  purifier = "helm-purifier";
  inherit problems;
  outputs = {
    chart = { };
  };
  entries =
    if problems != [ ] then
      [ ]
    else
      map (dep: {
        path = "${dep.key}.tgz";
        inherit (artifacts.${dep.key}) url hash;
        mirrors = [ ];
      }) decoded;
}
