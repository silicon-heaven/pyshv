{
  description = "Flake for Pure Python SHV implementation";

  inputs.flakepy.url = "gitlab:Cynerd/flakepy";

  outputs = {
    self,
    flakepy,
    nixpkgs,
  }: let
    inherit (flakepy.inputs.flake-utils.lib) eachDefaultSystem;
    inherit (nixpkgs.lib) getExe';

    pyproject = flakepy.lib.readPyproject ./. {};

    pypackage = pyproject.buildPackage {};
  in
    {
      overlays = {
        pythonPackages = final: _: {
          "${pyproject.pname}" = final.callPackage pypackage {};
        };
        pkgs = _: prev: {
          pythonPackagesExtensions =
            prev.pythonPackagesExtensions ++ [self.overlays.pythonPackages];
        };
        default = self.overlays.pkgs;
      };

      nixosModules = import ./nixos/modules {
        inherit (nixpkgs) lib;
        inherit (self) overlays;
      };
    }
    // eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system}.extend self.overlays.default;
    in {
      packages.default = pkgs.python3Packages."${pyproject.pname}";
      legacyPackages = pkgs;

      devShells.default = pkgs.mkShell {
        packages = with pkgs; [
          deadnix
          editorconfig-checker
          gitlint
          mypy
          ruff
          shellcheck
          shfmt
          statix
          twine
          (python3.withPackages (pypkgs:
              with pypkgs; [build sphinx-autobuild]))
        ];
        inputsFrom = [self.packages.${system}.default];
      };

      apps = {
        default = self.apps.${system}.pyshvbroker;
        pycp2cp = {
          type = "app";
          program = getExe' self.packages.${system}.default "pycp2cp";
        };
        pyshvbroker = {
          type = "app";
          program = getExe' self.packages.${system}.default "pyshvbroker";
        };
      };

      checks =
        import ./nixos/tests nixpkgs.lib pkgs self.nixosModules
        // {inherit (self.packages.${system}) default;};

      formatter = pkgs.alejandra;
    });
}
