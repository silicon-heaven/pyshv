{
  description = "Flake for Pure Python SHV implementation";

  inputs = {
    libshv.url = "git+https://github.com/silicon-heaven/libshv.git?submodules=1";
  };

  outputs = {
    self,
    flake-utils,
    nixpkgs,
    libshv,
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
        setuptools,
        sphinxHook,
        pytestCheckHook,
        libshv,
      }:
        buildPythonPackage {
          pname = pyproject.project.name;
          version = fileContents ./shv/version;
          format = "pyproject";
          src = builtins.path {
            path = ./.;
            filter = path: type: ! hasSuffix ".nix" path;
          };
          outputs = ["out" "doc"];
          propagatedBuildInputs = requires pythonPackages;
          nativeBuildInputs = [setuptools sphinxHook] ++ requires-docs pythonPackages;
          nativeCheckInputs = [pytestCheckHook libshv] ++ requires-test pythonPackages;
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

      pypkg-types-serial = {
        buildPythonPackage,
        fetchPypi,
      }:
        buildPythonPackage rec {
          pname = "types-pyserial";
          version = "3.5.0.10";
          src = fetchPypi {
            inherit pname version;
            hash = "sha256-libfaTGzM0gtBZZrMupSoUGj0ZyccPs8/vkX9x97bS0=";
          };
          doCheck = false;
          pythonImportsCheck = ["serial-stubs"];
        };
    in
      {
        overlays = {
          pythonPackagesExtension = final: prev: {
            pyshv = final.callPackage pypkg-pyshv {};
            sphinx-multiversion = final.callPackage pypkg-multiversion {};
            types-pyserial = final.callPackage pypkg-types-serial {};
          };
          noInherit = final: prev: {
            pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [self.overlays.pythonPackagesExtension];
          };
          default = composeManyExtensions [
            libshv.overlays.default
            self.overlays.noInherit
          ];
        };
      }
      // eachDefaultSystem (system: let
        pkgs = nixpkgs.legacyPackages.${system}.extend self.overlays.default;
      in {
        packages.default = pkgs.python3Packages.pyshv;
        legacyPackages = pkgs;

        devShells = filterPackages system {
          default = pkgs.mkShell {
            packages = with pkgs; [
              editorconfig-checker
              gitlint
              pkgs.libshv
              (python3.withPackages (p:
                [p.sphinx-autobuild]
                ++ foldl (prev: f: prev ++ f p) [] [
                  requires
                  requires-docs
                  requires-test
                  requires-dev
                ]))
            ];
          };
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

        checks.default = self.packages.${system}.default;

        formatter = pkgs.alejandra;
      });
}
