{
  description = "Flake for Pure Python SHV implementation";

  inputs.flakepy.url = "gitlab:Cynerd/flakepy";

  outputs = {
    self,
    flake-utils,
    nixpkgs,
    flakepy,
  }: let
    inherit (flake-utils.lib) eachDefaultSystem;
    inherit (nixpkgs.lib) composeManyExtensions;

    pyproject = flakepy.lib.pyproject ./. {};

    pypackage = {
      python,
      pytestCheckHook,
      sphinxHook,
    }:
      pyproject.buildPackage python {
        outputs = ["out" "doc"];
        nativeBuildInputs = [sphinxHook] ++ pyproject.optional-dependencies.docs python.pkgs;
        nativeCheckInputs = [pytestCheckHook] ++ pyproject.optional-dependencies.test python.pkgs;
      };
  in
    {
      overlays = {
        pythonPackages = final: _: {
          "${pyproject.pname}" = final.callPackage pypackage {};
        };
        packages = _: prev: {
          pythonPackagesExtensions =
            prev.pythonPackagesExtensions ++ [self.overlays.pythonPackages];
        };
        default = composeManyExtensions [self.overlays.packages];
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
          (python3.withPackages (pypkgs: with pypkgs; [build sphinx-autobuild]))
        ];
        inputsFrom = [self.packages.${system}.default];
      };

      apps = {
        default = self.apps.${system}.pyshvbroker;
        pycp2cp = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/pycp2cp";
        };
        pyshvbroker = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/pyshvbroker";
        };
      };

      checks =
        import ./nixos/tests nixpkgs.lib pkgs self.nixosModules
        // {inherit (self.packages.${system}) default;};

      formatter = pkgs.alejandra;
    });
}
