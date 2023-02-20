{
  description = "Project template for Python";

  outputs = {
    self,
    flake-utils,
    nixpkgs,
  }:
    with builtins;
    with flake-utils.lib;
    with nixpkgs.lib; let
      requires = p:
        with p; [
        ];
      requires-dev = p:
        with p; [
          black
          isort
          mypy
          pydocstyle
          pylint
          pytest
          pytest-cov
          twine
        ];

      pypkgs-template-python = {
        buildPythonPackage,
        pytestCheckHook,
      }: let
        pyproject = trivial.importTOML ./pyproject.toml;
      in
        buildPythonPackage {
          pname = pyproject.project.name;
          inherit (pyproject.project) version;
          src = ./.;
          nativeCheckInputs = [pytestCheckHook];
        };

      pyOverlay = pyself: pysuper: {
        template-python = pypkgs-template-python;
      };
    in
      {
        overlays.default = final: prev: {
          python3 = prev.python3.override pyOverlay;
          python3Packages = prev.python3.pkgs;
        };
      }
      // eachDefaultSystem (system: let
        pkgs = nixpkgs.legacyPackages.${system};
        pkgsSelf = self.packages.${system};
        devPython = pkgs.python3.withPackages (p: (requires p) ++ (requires-dev p));
      in {
        packages = {
          template-python = pkgs.python3Packages.callPackage pypkgs-template-python {};
          default = pkgsSelf.template-python;
        };
        legacyPackages = pkgs.extend self.overlays.default;

        devShells = filterPackages system {
          default = pkgs.mkShell {
            packages = with pkgs; [
              devPython
              editorconfig-checker
              gitlint
            ];
          };
        };

        checks.default = pkgsSelf.template-python;

        formatter = pkgs.alejandra;
      });
}
