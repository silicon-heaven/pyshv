{
  description = "Project Template Python";

  inputs.flakepy.url = "gitlab:Cynerd/flakepy";

  outputs = {
    self,
    systems,
    flakepy,
    nixpkgs,
  }: let
    inherit (nixpkgs.lib) genAttrs composeManyExtensions;
    forSystems = genAttrs (import systems);
    withPkgs = func: forSystems (system: func self.legacyPackages.${system});

    pyproject = flakepy.lib.readPyproject ./. {
      # This extends mapping of python to nixpkgs package names, such as:
      # pytest-asyncio = "pytest-asyncio_0_21";
    };

    pypackage = pyproject.buildPackage {
      meta.mainProgram = "template_package_name";
    };
  in {
    overlays = {
      pythonPackages = final: _: {
        "${pyproject.pname}" = final.callPackage pypackage {};
      };
      packages = _: prev: {
        pythonPackagesExtensions =
          prev.pythonPackagesExtensions ++ [self.overlays.pythonPackages];
      };
      default = composeManyExtensions [
        self.overlays.packages
      ];
    };

    packages = withPkgs (pkgs: {
      default = pkgs.python3Packages."${pyproject.pname}";
    });

    devShells = withPkgs (pkgs: {
      default = pkgs.mkShell {
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
        inputsFrom = [pkgs.python3Packages."${pyproject.pname}"];
      };
    });

    checks = forSystems (system: {
      inherit (self.packages.${system}) default;
    });
    formatter = withPkgs (pkgs: pkgs.alejandra);

    legacyPackages =
      forSystems (system:
        nixpkgs.legacyPackages.${system}.extend self.overlays.default);
  };
}
