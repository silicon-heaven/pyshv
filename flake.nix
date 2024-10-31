{
  description = "Flake for Pure Python SHV implementation";

  outputs = {
    self,
    flake-utils,
    nixpkgs,
  }: let
    inherit (builtins) match;
    inherit (flake-utils.lib) eachDefaultSystem filterPackages;
    inherit (nixpkgs.lib) head foldl trivial hasSuffix attrValues getAttrs composeManyExtensions;

    pyproject = trivial.importTOML ./pyproject.toml;
    inherit (pyproject.project) name version;
    src = builtins.path {
      path = ./.;
      filter = path: _: ! hasSuffix ".nix" path;
    };

    pypi2nix = list: pypkgs:
      attrValues (getAttrs (map (n: let
          pyname = head (match "([^ =<>;]*).*" n);
          pymap = {};
        in
          pymap."${pyname}" or pyname)
        list)
        pypkgs);
    requires = pypi2nix pyproject.project.dependencies;
    requires-test = pypi2nix pyproject.project.optional-dependencies.test;
    requires-docs = pypi2nix pyproject.project.optional-dependencies.docs;

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

    pypackage = {
      buildPythonPackage,
      pytestCheckHook,
      pythonPackages,
      setuptools,
      sphinxHook,
    }:
      buildPythonPackage {
        pname = pyproject.project.name;
        inherit version src;
        pyproject = true;
        build-system = [setuptools];
        outputs = ["out" "doc"];
        propagatedBuildInputs = requires pythonPackages;
        nativeBuildInputs = [sphinxHook] ++ requires-docs pythonPackages;
        nativeCheckInputs = [pytestCheckHook] ++ requires-test pythonPackages;
      };
  in
    {
      overlays = {
        pythonPackagesExtension = final: _: {
          sphinx-multiversion = final.callPackage multiversion {};
          types-pyserial = final.callPackage types-serial {};
          "${name}" = final.callPackage pypackage {};
        };
        noInherit = _: prev: {
          pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [self.overlays.pythonPackagesExtension];
        };
        default = composeManyExtensions [self.overlays.noInherit];
      };

      nixosModules = import ./nixos/modules {
        inherit (nixpkgs) lib;
        inherit (self) overlays;
      };
    }
    // eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system}.extend self.overlays.default;
    in {
      packages.default = pkgs.python3Packages."${name}";
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
