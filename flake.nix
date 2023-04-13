{
  description = "Flake for Pure Python SHV implementation";

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
          attrList p pyproject.project.optional-dependencies.docs
          ++ attrList p pyproject.project.optional-dependencies.test
          ++ [twine];

      pypkg-pyshv = {
        buildPythonPackage,
        pipBuildHook,
        setuptools,
        pytestCheckHook,
      }:
        buildPythonPackage {
          pname = pyproject.project.name;
          inherit (pyproject.project) version;
          src = ./.;
          nativeBuildInputs = [pipBuildHook setuptools];
          nativeCheckInputs = [pytestCheckHook];
          dontUseSetuptoolsBuild = true;
          doCheck = false;
        };

      pyOverlay = pyself: pysuper: {
        pyshv = pyself.callPackage pypkg-pyshv {};
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
          pyshv = pkgs.python3Packages.callPackage pypkg-pyshv {};
          default = pkgsSelf.pyshv;
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

        checks.default = pkgsSelf.pyshv;

        formatter = pkgs.alejandra;
      });
}
