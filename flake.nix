{
  description = "Project Template Python";

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
          pyname = head (match "([^ =<>;~]*).*" n);
          pymap = {
          };
        in
          pymap."${pyname}" or pyname)
        list)
        pypkgs);
    requires = pypi2nix pyproject.project.dependencies;
    requires-test = pypi2nix pyproject.project.optional-dependencies.test;
    requires-docs = pypi2nix pyproject.project.optional-dependencies.docs;

    pypackage = {
      buildPythonPackage,
      python,
      pytestCheckHook,
      setuptools,
      sphinxHook,
    }:
      buildPythonPackage {
        pname = pyproject.project.name;
        inherit version src;
        pyproject = true;
        build-system = [setuptools];
        outputs = ["out" "doc"];
        propagatedBuildInputs = requires python.pkgs;
        nativeBuildInputs = [sphinxHook] ++ requires-docs python.pkgs;
        nativeCheckInputs = [pytestCheckHook] ++ requires-test python.pkgs;
        meta.mainProgram = "template_package_name";
      };
  in
    {
      overlays = {
        pythonPackages = final: _: {
          "${name}" = final.callPackage pypackage {};
        };
        pkgs = _: prev: {
          pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [self.overlays.pythonPackages];
        };
        default = composeManyExtensions [
          self.overlays.pkgs
        ];
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
            deadnix
            editorconfig-checker
            gitlint
            ruff
            shellcheck
            shfmt
            statix
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

      checks.default = self.packages.${system}.default;

      formatter = pkgs.alejandra;
    });
}
