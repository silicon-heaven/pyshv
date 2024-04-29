{
  pkgs,
  nixosModules,
  ...
}: let
  testPython = pkgs.python3.withPackages (p: [p.pyshv p.mypy p.black]);
  shvTest = name: script:
    pkgs.writeTextFile {
      inherit name;
      destination = "/bin/${name}";
      meta.mainProgram = name;
      executable = true;
      text = ''
        #!${testPython}/bin/python3
        import asyncio
        import shv


        ${script}

        asyncio.run(main())
      '';
      checkPhase = ''
        ${testPython}/bin/python -m mypy "$target"
        ${pkgs.ruff}/bin/ruff check "$target"
        ${pkgs.black}/bin/black --check --diff "$target"
      '';
    };
in {
  nodes = {
    broker = {
      imports = [nixosModules.default];
      environment.etc.adminpass.text = "admin!123";
      services.pyshvbroker = {
        enable = true;
        openFirewall = true;
        logLevel = "DEBUG";
        config = {
          users.admin = {
            passwordFile = "/etc/adminpass";
            roles = ["admin"];
          };
          roles.admin = {
            access = "su";
            match = ["**"];
          };
        };
      };
    };
    client = {
      environment.systemPackages = [
        (shvTest "checkls" ''
          async def main():
              url = shv.RpcUrl("broker", 3755, login=shv.RpcLogin("admin", "admin!123"))
              client = await shv.SimpleClient.connect(url)
              assert await client.ls("") == [".app", ".broker"]
              await client.disconnect()
        '')
      ];
    };
  };

  testScript = ''
    start_all()
    broker.wait_for_open_port(3755)
    client.wait_for_open_port(3755, "broker")

    with subtest("List top level nodes"):
      client.succeed("checkls")
  '';
}
