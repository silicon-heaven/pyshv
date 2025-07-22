{
  description = "Flake for Pure Python SHV implementation";

  inputs.flakepy.url = "gitlab:Cynerd/flakepy";

  outputs = {
    self,
    flakepy,
    nixpkgs,
  }: let
    inherit (nixpkgs.lib) genAttrs getExe';
    forSystems = genAttrs (import flakepy.inputs.systems);
    withPkgs = func: forSystems (system: func self.legacyPackages.${system});

    pyproject = flakepy.lib.readPyproject ./. {};

    pypackage = pyproject.buildPackage (
      {
        lib,
        optional-dependencies,
        nativeCheckInputs,
      }: {
        nativeCheckInputs = nativeCheckInputs ++ optional-dependencies.websockets;
        meta = {
          inherit (pyproject.pyproject.project) description;
          homepage = "https://silicon-heaven.gitlab.io/";
          license = lib.licenses.mit;
          maintainers = [lib.maintainers.cynerd];
          platforms = lib.platforms.all;
        };
      }
    );
  in {
    overlays = {
      pythonPackages = final: _: {
        "${pyproject.pname}" = final.callPackage pypackage {};
      };
      pkgs = _: prev: {
        pythonPackagesExtensions =
          prev.pythonPackagesExtensions ++ [self.overlays.pythonPackages];
      };
      default = self.overlays.pkgs;
    };

    nixosModules = import ./nixos/modules {
      inherit (nixpkgs) lib;
      inherit (self) overlays;
    };

    legacyPackages =
      forSystems (system:
        nixpkgs.legacyPackages.${system}.extend self.overlays.default);

    packages = withPkgs (pkgs: {
      default = pkgs.python3Packages."${pyproject.pname}";
    });

    apps = forSystems (system: {
      default = self.apps.${system}.pyshvbroker;
      pycp2cp = {
        type = "app";
        program = getExe' self.packages.${system}.default "pycp2cp";
        meta.description = "Chainpack <-> CPON conversion tool";
      };
      pyshvbroker = {
        type = "app";
        program = getExe' self.packages.${system}.default "pyshvbroker";
        meta.description = "SHV RPC Broker application";
      };
    });

    devShells = withPkgs (pkgs: {
      default = pkgs.mkShell {
        packages = with pkgs; [
          deadnix
          editorconfig-checker
          gitlint
          mypy
          ruff
          shellcheck
          shfmt
          statix
          twine
          (python3.withPackages (pypkgs:
              with pypkgs; [build sphinx-autobuild]))
        ];
        inputsFrom = [pkgs.python3Packages."${pyproject.pname}"];
      };
    });

    checks = withPkgs (pkgs:
      import ./nixos/tests nixpkgs.lib.nixos pkgs self.nixosModules
      // {
        python311 = pkgs.python311Packages."${pyproject.pname}";
        python312 = pkgs.python312Packages."${pyproject.pname}";
        python313 = pkgs.python313Packages."${pyproject.pname}";
      });

    formatter = withPkgs (pkgs: pkgs.alejandra);
  };
}
