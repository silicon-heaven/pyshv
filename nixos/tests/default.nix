nixos: pkgs: nixosModules: let
  inherit (pkgs.lib) mapAttrs' nameValuePair filterAttrs removeSuffix hasSuffix;
  inherit (builtins) readDir;

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
    filterAttrs (n: v: v == "regular" && hasSuffix ".nix" n && n != "default.nix") (
      readDir ./.
    )
  )
