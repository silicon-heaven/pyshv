lib: pkgs: nixosModules:
with builtins;
with lib; let
  runTest = path: name: let
    modtest = import path {inherit nixosModules pkgs;};
  in
    nixos.runTest (modtest
      // {
        name = modtest.name or name;
        hostPkgs = modtest.hostPkgs or pkgs;
      });
in
  mapAttrs' (
    name: _: let
      nname = removeSuffix ".nix" name;
    in
      nameValuePair nname (runTest (./. + "/${name}") nname)
  )
  (
    filterAttrs (n: v: v == "regular" && hasSuffix ".nix" n) (
      readDir ./.
    )
  )
