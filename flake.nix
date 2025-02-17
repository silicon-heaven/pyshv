{
  description = "Project Template Python";

  inputs.flakepy.url = "gitlab:Cynerd/flakepy";

  outputs = {
    self,
    flakepy,
    nixpkgs,
  }: let
    inherit (flakepy.inputs.flake-utils.lib) eachDefaultSystem;
    inherit (nixpkgs.lib) composeManyExtensions;

    pyproject = flakepy.lib.readPyproject ./. {
      # This extends mapping of python to nixpkgs package names, such as:
      # pytest-asyncio = "pytest-asyncio_0_21";
    };

    pypackage = pyproject.buildPackage {
      meta.mainProgram = "template_package_name";
    };
  in
    {
      overlays = {
        pythonPackages = final: _: {
          "${pyproject.pname}" = final.callPackage pypackage {};
        };
        pkgs = _: prev: {
          pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [self.overlays.pythonPackages];
        };
        default = composeManyExtensions [
          self.overlays.pkgs
        ];
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

      checks.default = self.packages.${system}.default;

      formatter = pkgs.alejandra;
    });
}
