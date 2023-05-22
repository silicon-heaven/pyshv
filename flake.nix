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
      requires-docs = p: attrList p pyproject.project.optional-dependencies.docs;
      requires-test = p: attrList p pyproject.project.optional-dependencies.test;
      requires-dev = p:
        attrList p pyproject.project.optional-dependencies.lint
        ++ [p.build p.twine];

      pypkg-pyshv = {
        buildPythonPackage,
        pythonPackages,
        sphinxHook,
        pytestCheckHook,
        shvapp,
      }:
        buildPythonPackage {
          pname = pyproject.project.name;
          inherit (pyproject.project) version;
          format = "pyproject";
          src = builtins.path {
            path = ./.;
            filter = path: type: ! hasSuffix ".nix" path;
          };
          outputs = ["out" "doc"];
          propagatedBuildInputs = requires pythonPackages;
          nativeBuildInputs = [sphinxHook] ++ requires-docs pythonPackages;
          nativeCheckInputs = [pytestCheckHook shvapp] ++ requires-test pythonPackages;
        };

      pypkg-multiversion = {
        buildPythonPackage,
        fetchFromGitHub,
        sphinx,
      }:
        buildPythonPackage {
          pname = "sphinx-multiversion";
          version = "0.2.4";
          src = fetchFromGitHub {
            owner = "Holzhaus";
            repo = "sphinx-multiversion";
            rev = "v0.2.4";
            hash = "sha256-ZFEELAeZ/m1pap1DmS4PogL3eZ3VuhTdmwDOg5rKOPA=";
          };
          propagatedBuildInputs = [sphinx];
          doCheck = false;
        };
    in
      {
        overlays = {
          pyshv = final: prev: {
            python3 = prev.python3.override {
              packageOverrides = pyfinal: pyprev: {
                pyshv = pyfinal.callPackage pypkg-pyshv {};
                sphinx-multiversion = pyfinal.callPackage pypkg-multiversion {};
              };
            };
            python3Packages = final.python3.pkgs;
          };
          default = composeManyExtensions [
            shvapp.overlays.default
            self.overlays.pyshv
          ];
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
                [
                  p.sphinx-autobuild
                ] ++ foldl (prev: f: prev ++ f p) [] [
                  requires
                  requires-docs
                  requires-test
                  requires-dev
                ]))
            ];
          };
        };

        checks.default = self.packages.${system}.default;

        formatter = pkgs.alejandra;
      });
}
