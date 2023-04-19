{
  description = "Flake for Pure Python SHV implementation";

  inputs = {
    shvapp.url = "git+https://github.com/silicon-heaven/shvapp.git?submodules=1";
  };

  outputs = {
    self,
    flake-utils,
    nixpkgs,
    shvapp,
  }:
    with builtins;
    with flake-utils.lib;
    with nixpkgs.lib; let
      pyproject = trivial.importTOML ./pyproject.toml;
      attrList = attr: list: attrValues (getAttrs list attr);

      requires = p: attrList p pyproject.project.dependencies;
      requires-test = p: attrList p pyproject.project.optional-dependencies.test;
      requires-dev = p:
          attrList p pyproject.project.optional-dependencies.docs
          ++ attrList p pyproject.project.optional-dependencies.lint
          ++ [p.build p.twine];

      pypkg-pyshv = {
        buildPythonPackage,
        pipBuildHook,
        setuptools,
        pytestCheckHook,
        pythonPackages,
        shvapp,
      }:
        buildPythonPackage {
          pname = pyproject.project.name;
          inherit (pyproject.project) version;
          src = ./.;
          nativeBuildInputs = [pipBuildHook setuptools];
          nativeCheckInputs = [pytestCheckHook shvapp] ++ requires-test pythonPackages;
          dontUseSetuptoolsBuild = true;
        };
    in
      {
        overlays = {
          pyshv = final: prev: {
            python3 = prev.python3.override {
              packageOverrides = pyfinal: pyprev: {
                pyshv = pyfinal.callPackage pypkg-pyshv {};
              };
            };
            python3Packages = final.python3.pkgs;
          };
          default = composeExtensions shvapp.overlays.default self.overlays.pyshv;
        };
      }
      // eachDefaultSystem (system: let
        pkgs = nixpkgs.legacyPackages.${system}.extend self.overlays.default;
      in {
        packages = {
          inherit (pkgs.python3Packages) pyshv;
          default = self.packages.${system}.pyshv;
        };
        legacyPackages = pkgs;

        devShells = filterPackages system {
          default = pkgs.mkShell {
            packages = with pkgs; [
              editorconfig-checker
              gitlint
              pkgs.shvapp
              (python3.withPackages (p:
                foldl (prev: f: prev ++ f p) [] [
                  requires
                  requires-dev
                  requires-test
                ]))
            ];
          };
        };

        checks.default = self.packages.${system}.default;

        formatter = pkgs.alejandra;
      });
}
