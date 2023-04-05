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
      pyproject = trivial.importTOML ./pyproject.toml;
      attrList = attr: list: attrValues (getAttrs list attr);

      requires = p: attrList p pyproject.project.dependencies;
      requires-dev = p:
        with p;
          attrList p pyproject.project.optional-dependencies.test
          ++ [twine];

      pypkgs-template-python = {
        buildPythonPackage,
        pytestCheckHook,
        pythonPackages,
      }:
        buildPythonPackage {
          pname = pyproject.project.name;
          inherit (pyproject.project) version;
          src = ./.;
          propagatedBuildInputs = requires pythonPackages;
          nativeCheckInputs = [pytestCheckHook];
        };

      pyOverlay = pyself: pysuper: {
        template-python = pyself.callPackage pypkgs-template-python {};
      };
    in
      {
        overlays.default = final: prev: {
          python3 = prev.python3.override {packageOverrides = pyOverlay;};
          python3Packages = final.python3.pkgs;
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
