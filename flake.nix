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
          attrList p pyproject.project.optional-dependencies.test
          ++ [twine];

      pypkg-libshv-py = {
        buildPythonPackage,
        pytestCheckHook,
      }:
        buildPythonPackage {
          pname = pyproject.project.name;
          inherit (pyproject.project) version;
          src = ./.;
          nativeCheckInputs = [pytestCheckHook];
        };

      pyOverlay = pyself: pysuper: {
        libshv-py = pypkg-libshv-py;
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
          libshv-py = pkgs.python3Packages.callPackage pypkg-libshv-py {};
          default = pkgsSelf.libshv-py;
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

        checks.default = pkgsSelf.libshv-py;

        formatter = pkgs.alejandra;
      });
}
