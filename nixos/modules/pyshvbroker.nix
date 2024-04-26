{
  config,
  lib,
  pkgs,
  ...
}: let
  inherit (builtins) attrNames attrValues match filter elemAt;
  inherit (lib) mkEnableOption mkOption types mkIf;
  inherit (lib) all count foldl mapAttrs strings optionalString filterAttrsRecursive;
  cfg = config.services.pyshvbroker;

  conf = filterAttrsRecursive (_: v: v != null) (mapAttrs (cn: cv:
    if cn == "users"
    then
      (mapAttrs (un: uv:
        uv
        // {
          password =
            if uv.passwordFile != null
            then "@PASSWORD_${un}@"
            else uv.password;
          sha1pass =
            if uv.sha1passFile != null
            then "@PASSWORD_${un}@"
            else uv.sha1pass;
          passwordFile = null; # unset so it is filtered out
          sha1passFile = null; # unset  so it is filtered out
        })
      cv)
    else cv)
  cfg.config);
in {
  options = {
    services.pyshvbroker = {
      enable = mkEnableOption "Enable Silicon Heaven (Python) Broker service.";

      config = mkOption {
        type = types.submodule {
          options = {
            listen = mkOption {
              type = with types; attrsOf str;
              default = {tcp = "tcp://[::]:3755";};
              description = ''
                This specifies URLs where server should listen for the new
                connections. The keys are only informative and used for
                identification purpose (feel free to name them as ever you
                want).
              '';
            };

            connect = mkOption {
              type = types.attrsOf (types.submodule {
                options = {
                  url = mkOption {
                    type = types.str;
                    description = "Where to connect including the login information.";
                  };
                  user = mkOption {
                    type = types.str;
                    description = ''
                      User that connected client gets assigned to. This is user
                      of this broker (not the remote one).
                    '';
                  };
                };
              });
              default = {};
              description = ''
                Define connection to some other SHV Broker that is initiated by
                this broker.
              '';
            };

            users = mkOption {
              type = types.attrsOf (types.submodule {
                options = {
                  password = mkOption {
                    type = with types; nullOr str;
                    default = null;
                    description = ''
                      Plain text password that is required to be provided by
                      client when connecting to the broker. This allows user to
                      use `PLAIN` and `SHA1` login methods. If you do not
                      specify this option (nor `sha1pass`) then this user
                      won't be used for login but still can be used as user for
                      connect.
                    '';
                  };
                  passwordFile = mkOption {
                    type = with types; nullOr str;
                    default = null;
                    description = ''
                      Same as `password` but read it from file before service
                      start. This is advantageous if you do not want to have
                      passwords in Nix store (which is prefered).
                    '';
                  };
                  sha1pass = mkOption {
                    type = with types; nullOr str;
                    default = null;
                    description = ''
                      Password hashed with SHA1 hash that is required to be
                      provided by client when connecting to the broker. This
                      allow user to use only `SHA` login method but has
                      advantage that password is not stored in plain text on
                      server.
                    '';
                  };
                  sha1passFile = mkOption {
                    type = with types; nullOr str;
                    default = null;
                    description = ''
                      Same as `sh1pass` but read it from file before service
                      start. This is advantageous if you do not want to have
                      passwords in Nix store (which is prefered).
                    '';
                  };
                  roles = mkOption {
                    type = with types; listOf str;
                    default = [];
                    description = "List of roles assigned to the user.";
                  };
                };
              });
              description = "Users allowed to login to the Broker." "";
            };

            roles = mkOption {
              type = types.attrsOf (types.submodule {
                options = {
                  access = mkOption {
                    type = types.enum ["bws" "rd" "wr" "cmd" "cfg" "srv" "ssrv" "dev" "su"];
                    default = "bws";
                    description = ''
                      Access level granted to the user with this role for
                      matching methods. Note that access level of the first role
                      that has at least one matching rule is used. The ordering
                      of the roles can be used to specify complex access rules.
                    '';
                  };
                  methods = mkOption {
                    type = with types; listOf str;
                    default = [];
                    description = ''
                      Specifies list of path and method pairs this role applies
                      on. The path and method is delimited with `:` and empty
                      method matches all methods. And thus `foo:` matches all
                      methods associated with node `foo` and its children. The
                      sole `:` used in example matches all methods from root
                      node and thus specifies the role to apply to all nodes and
                      methods.
                    '';
                  };
                };
              });
              default = {};
              description = ''
                Roles are groupings of rules that are assigned to the users.
                They provide versatility in the configuration.
              '';
            };
          };
        };
        description = "Silicon Heaven Broker configuration.";
      };

      logLevel = mkOption {
        type = types.enum ["CRITICAL" "FATAL" "ERROR" "WARN" "WARNING" "INFO" "DEBUG"];
        default = "INFO";
        description = "Verbosity level for brokers logging.";
      };

      openFirewall = mkEnableOption ''
        Open the configured TCP/IP port (config.server.port) in Firewall.
      '';
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = all (v:
          (count (p: p != null) [
            v.password
            v.passwordFile
            v.sha1pass
            v.sha1passFile
          ])
          <= 1)
        (attrValues cfg.config.users);
        message = "Options password, passwordFile, sha1pass and sha1passFile are exclusive and can't be used toggether";
      }
      {
        assertion =
          all (v: cfg.config.roles ? "${v}") (foldl (prev: v: prev ++ v.roles) []
            (attrValues cfg.config.users));
        message = "All roles specified for the users must be defined.";
      }
      {
        assertion =
          all (v: cfg.config.users ? "${v}") (foldl (prev: v: prev ++ [v.user]) []
            (attrValues cfg.config.connect));
        message = "All users specified for the connect must be defined.";
      }
    ];

    systemd.services.pyshvbroker = {
      description = "Silicon Heaven Broker";
      wantedBy = ["multi-user.target"];
      preStart = ''
        umask 077
        {
          while read -r line; do
        ${foldl (
          prev: name: let
            v = cfg.config.users."${name}";
            file =
              if v.passwordFile != null
              then v.passwordFile
              else v.sha1passFile;
          in
            prev
            + (
              optionalString (file != null)
              ''
                line="''${line/@PASSWORD_${name}@/$(cat '${file}')}"
              ''
            )
        ) "" (attrNames cfg.config.users)}
            printf '%s\n' "$line"
          done
        } >"$RUNTIME_DIRECTORY/config.toml" <${
          (pkgs.formats.toml {}).generate "pyshvbroker.toml" conf
        }
      '';
      serviceConfig = {
        ExecStart = ''
          ${pkgs.python3Packages.pyshv}/bin/pyshvbroker --log-level ${cfg.logLevel} -c ''${RUNTIME_DIRECTORY}/config.toml
        '';
        RuntimeDirectory = "pyshvbroker";
      };
    };

    networking.firewall.allowedTCPPorts =
      mkIf cfg.openFirewall
      (map (v: strings.toIntBase10 (elemAt v 1))
        (filter (v: v != null)
          (map (v: match "(tcp|tcps|ws|wss)://[^\\?]*:([0-9]+)(\\?.*)?" v)
            (attrValues cfg.config.listen))));
  };
}
