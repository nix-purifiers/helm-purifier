# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  kubernetes-helm,
  helm-ls,
  yaml-language-server,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  python = python3.withPackages (p: [ p.pyyaml ]);
in
stdenvNoCC.mkDerivation {
  pname = "helm-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/helm-purifier"
    cp -r helm_purifier pkgs lib-overlays "$out/lib/helm-purifier/"
    install -m755 bin/helm-purifier "$out/bin/helm-purifier"
    substituteInPlace "$out/lib/helm-purifier/pkgs/build-helm-project/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}' \
      --replace-fail '@runtime@' "$out"
    wrapProgram "$out/bin/helm-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python
          nix
          kubernetes-helm
          helm-ls
          yaml-language-server
        ]
      } \
      --prefix PYTHONPATH : "$out/lib/helm-purifier" \
      --set HELM_PURIFIER_HELM ${kubernetes-helm}/bin/helm \
      --set HELM_PURIFIER_REALIZE "$out/lib/helm-purifier/pkgs/build-helm-project/realize.nix" \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt
    ln -s ${kubernetes-helm}/bin/helm "$out/bin/helm"
    makeWrapper ${helm-ls}/bin/helm_ls "$out/bin/helm_ls" --prefix PATH : ${
      lib.makeBinPath [
        kubernetes-helm
        yaml-language-server
      ]
    }
    ln -s ${yaml-language-server}/bin/yaml-language-server "$out/bin/yaml-language-server"
  '';
  meta = {
    description = "Helm dependencies resolved and retained by Nix";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "helm-purifier";
    homepage = "https://nix-purifiers.github.io/";
  };
}
