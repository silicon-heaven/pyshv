{
  config,
  lib,
  pkgs,
  ...
}: let
  inherit (builtins) attrNames attrValues match filter elemAt;
  inherit (lib) mkEnableOption mkOption types mkIf;
  inherit (lib) all count foldl mapAttrs strings optionalString filterAttrsRecursive;
  inherit (lib) genAttrs toList;
  cfg = config.services.pyshvbroker;
  access_levels = ["bws" "rd" "wr" "cmd" "cfg" "srv" "ssrv" "dev" "su"];

  conf = filterAttrsRecursive (_: v: v != null) (mapAttrs (cn: cv:
    if cn == "user"
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
            name = mkOption {
              type = types.str;
              default = "";
              description = ''
                The name of the broker. This is used when constructing ClientID
                to identify this broker. In default this is empty and thus only
                user's name is appended but if you specify it then user name
                will be prefixed with this name (forming `localhost:foo` for
                `name = localhost` and user `foo`).
              '';
            };

            listen = mkOption {
              type = with types; listOf str;
              default = ["tcp://[::]:3755"];
              description = ''
                This specifies URLs where server should listen for the new
                connections.
              '';
            };

            connect = mkOption {
              type = types.listOf (types.submodule {
                options = {
                  url = mkOption {
                    type = types.str;
                    description = "Where to connect including the login information.";
                  };
                  role = mkOption {
                    type = with types; either str (listOf str);
                    default = ["default"];
                    description = ''
                      Role names to be used to control access of the connected
                      peer on this broker.
                    '';
                  };
                  mountPoint = mkOption {
                    type = with types; nullOr str;
                    default = null;
                    description = ''
                      Local mount point for the connected peer.
                    '';
                  };
                  subscriptions = mkOption {
                    type = with types; listOf str;
                    default = [];
                    description = ''
                      List of subscriptions in resource identifier format used
                      as an initial set of subscriptions this connection gets
                      assigned.
                    '';
                  };
                };
              });
              default = [];
              description = ''
                Define connection to some other SHV Brokers that is initiated by
                this one.
              '';
            };

            user = mkOption {
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
                  role = mkOption {
                    type = with types; either str (listOf str);
                    default = [];
                    description = "List of role names assigned to the user.";
                  };
                };
              });
              description = "Users allowed to login to the Broker." "";
            };

            role = mkOption {
              type = types.attrsOf (types.submodule {
                options = {
                  access = genAttrs access_levels (level:
                    mkOption {
                      type = with types; listOf str;
                      default = [];
                      description = ''
                        The list of resource identifiers providing access with
                        level ${level} to methods and signals matching it.
                      '';
                    });
                  mountPoints = mkOption {
                    type = with types; listOf str;
                    default = [];
                    description = ''
                      Wildcard patterns (rules from POSIX.2, 3.13) that limits
                      mount points user can request during login (option
                      `device.mountPoint`). If no role that user specifies has
                      this option then explicit mount point is not allowed. Note
                      that this doesn't limit mount point assigned by
                      `autosetup` nor `connect[].mountPoint`.
                    '';
                  };
                };
              });
              default = {};
              description = ''
                Roles are groupings of access rules that are assigned to the
                users and connections.
              '';
            };

            autosetup = mkOption {
              type = types.listOf (types.submodule {
                options = {
                  deviceId = mkOption {
                    type = with types; listOf str;
                    description = ''
                      Wildcard patterns (rules from POSIX.2, 3.13) for device ID
                      that client must supply in login option
                      ``device.deviceId`` to be considered for this setup.
                    '';
                  };
                  role = mkOption {
                    type = with types; either str (listOf str);
                    default = [];
                    description = ''
                      Role names that must be assigned to the user for this
                      autosetup to be considered. If not specified (emtpy list)
                      then all roles are considered.
                    '';
                  };
                  mountPoint = mkOption {
                    type = with types; nullOr str;
                    default = null;
                    description = ''
                      Printf-like format string to generate mount point client
                      will be automatically mounted to. This is used only if
                      client did not specify its own mount point with login
                      option `device.mountPoint`. The foramt string can contain
                      the following stand-ins:

                      * `%d` for device ID
                      * `%r` for the role user has assigned
                      * `%u` for the user's name
                      * `%i` for an unique number when mount point already
                        exists. For already unique mount points this is empty.
                      * `%I` for an unique number from zero to get an unique
                        mount point.
                      * `%%` for plain `%`
                    '';
                  };
                  subscriptions = mkOption {
                    type = with types; listOf str;
                    default = [];
                    description = ''
                      List of initial subscriptions in resource identifier
                      format used as an initial set of subscriptions this peer
                      gets assigned.
                    '';
                  };
                };
              });
              default = [];
              description = ''
                Auto-setups are used when peer logins with some user and
                specifies `device.deviceId`.
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
        (attrValues cfg.config.user);
        message = "Options password, passwordFile, sha1pass and sha1passFile are exclusive and can't be used toggether";
      }
      {
        assertion =
          all (v: cfg.config.role ? "${v}") (foldl (prev: v: prev ++ (toList v.role))
            [] (attrValues cfg.config.user));
        message = "All roles specified for the users must be defined.";
      }
      {
        assertion =
          all (v: cfg.config.role ? "${v}") (foldl (prev: v: prev ++ (toList v.role)) []
            cfg.config.connect);
        message = "All roles specified for the connect must be defined.";
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
            v = cfg.config.user."${name}";
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
        ) "" (attrNames cfg.config.user)}
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
            cfg.config.listen)));
  };
}
