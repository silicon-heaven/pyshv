{
  lib,
  overlays,
}: let
  inherit (builtins) readDir;
  inherit (lib) filterAttrs hasSuffix mapAttrs' nameValuePair removeSuffix attrValues;

  modules =
    mapAttrs'
    (fname: _: nameValuePair (removeSuffix ".nix" fname) (./. + ("/" + fname)))
    (filterAttrs (
      n: v:
        v == "regular" && n != "default.nix" && hasSuffix ".nix" n
    ) (readDir ./.));
in
  modules
  // {
    default = {
      imports = builtins.attrValues modules;
      config.nixpkgs.overlays = [overlays.default];
    };
  }
