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
          pyname = head (match "([^ =<>;]*).*" n);
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
        meta.mainProgram = "template_package_name";
      };
  in
    {
      overlays = {
        pythonPackagesExtension = final: _: {
          "${name}" = final.callPackage pypackage {};
        };
        noInherit = _: prev: {
          pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [self.overlays.pythonPackagesExtension];
        };
        default = composeManyExtensions [self.overlays.noInherit];
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

      checks.default = self.packages.${system}.default;

      formatter = pkgs.alejandra;
    });
}
