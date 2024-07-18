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
      src = builtins.path {
        path = ./.;
        filter = path: _: ! hasSuffix ".nix" path;
      };

      pypy2nix_map = {
        "pytest-asyncio" = "pytest-asyncio_0_21";
      };
      list2attr = list: attr: attrValues (getAttrs list attr);
      pypi2nix = list:
        list2attr (map (n: let
          nn = elemAt (match "([^ ;]*).*" n) 0;
        in
          pypy2nix_map.${nn} or nn)
        list);
      requires = pypi2nix pyproject.project.dependencies;
      requires-docs = pypi2nix pyproject.project.optional-dependencies.docs;
      requires-test = pypi2nix pyproject.project.optional-dependencies.test;

      pyshv = {
        buildPythonPackage,
        pythonPackages,
        setuptools,
        sphinxHook,
        pytestCheckHook,
      }:
        buildPythonPackage {
          pname = pyproject.project.name;
          inherit (pyproject.project) version;
          inherit src;
          pyproject = true;
          build-system = [setuptools];
          outputs = ["out" "doc"];
          propagatedBuildInputs = requires pythonPackages;
          nativeBuildInputs = [sphinxHook] ++ requires-docs pythonPackages;
          nativeCheckInputs = [pytestCheckHook] ++ requires-test pythonPackages;
        };

      multiversion = {
        buildPythonPackage,
        fetchFromGitHub,
        setuptools,
        sphinx,
      }:
        buildPythonPackage {
          pname = "sphinx-multiversion";
          version = "0.2.4";
          pyproject = true;
          build-system = [setuptools];
          src = fetchFromGitHub {
            owner = "Holzhaus";
            repo = "sphinx-multiversion";
            rev = "v0.2.4";
            hash = "sha256-ZFEELAeZ/m1pap1DmS4PogL3eZ3VuhTdmwDOg5rKOPA=";
          };
          propagatedBuildInputs = [sphinx];
          doCheck = false;
        };

      types-serial = {
        buildPythonPackage,
        fetchPypi,
        setuptools,
      }:
        buildPythonPackage rec {
          pname = "types-pyserial";
          version = "3.5.0.10";
          pyproject = true;
          build-system = [setuptools];
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
          pythonPackagesExtension = final: _: {
            pyshv = final.callPackage pyshv {};
            sphinx-multiversion = final.callPackage multiversion {};
            types-pyserial = final.callPackage types-serial {};
          };
          default = _: prev: {
            pythonPackagesExtensions =
              prev.pythonPackagesExtensions
              ++ [self.overlays.pythonPackagesExtension];
          };
        };
        nixosModules = import ./nixos/modules {
          inherit (nixpkgs) lib;
          inherit (self) overlays;
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
              statix
              deadnix
              gitlint
              ruff
              (python3.withPackages (p:
                [p.build p.twine p.sphinx-autobuild p.mypy]
                ++ foldl (prev: f: prev ++ f p) [] [
                  requires
                  requires-docs
                  requires-test
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

        checks =
          import ./nixos/tests nixpkgs.lib pkgs self.nixosModules
          // {inherit (self.packages.${system}) default;};

        formatter = pkgs.alejandra;
      });
}
