Running SHV RPC Broker in NixOS
===============================

This repository provides also integration to the Linux distribution NixOS. That
consists of the NixOS module that allows deployment of the ``pyshvbroker``
service.

The inclusion with Nix Flakes is consist of two steps:

* Adding this repository to your inputs::

    inputs.pyshv.url = "gitlab:silicon-heaven/pyshv";

* Including the provided default NixOS module in your configuration::

    import = [pysvh.nixosModules.default];

  The imported default module adds not only all modules provided by this
  repository, it also adds NixPkgs overlay so you have access to the pyshv
  package.


The NixOS module for ``pyshvbroker`` provides the following options that are all
located in ``services.pyshvbroker`` module:

:enable:
  The boolean option set in default to ``false``. This enables the SHV RPC
  Broker service.

:config.name:
  The string option that corresponds to the CLI configuration option of the same
  name. The default is the empty string.

:config.listen:
  The list of strings that corresponds to the CLI configuration option of the
  same name. The default is ``["tcp://[::]:3755"]``.

:config.connect:
  The list of modules that corresponds to the CLI configuration option of the
  same name. The default is empty list. The following options are expected:

  :url:
    The string option corresponding to the CLI configuration option of the same
    name.

  :role:
    The string or a list of strings corresponding to the CLI configuration
    option of the same name. The default is ``["default"]``.

  :mountPoint:
    The null or string option corresponding to the CLI configuration option of
    the same name. The default is ``null``.

  :subscriptions:
    The list of strings corresponding to the CLI configuration option of the
    same name. The default is empty list.

:config.user.<name>:
  The attribute set of the users defined in the broker. The ``<name>`` is to be
  the user's name. The user has the following options:

  :password:
    The null or string option corresponding to the CLI configuration option of
    the same name. The default is ``null``. Be aware that this includes this
    password in the Nix store in plain text form! Preferably use
    **passwordFile**.

  :passwordFile:
    The alternative way to specify **password** option. This is expected to be
    null or string with path to the file (on the NixOS machine) containing the
    password to be used. This is preferred way of specifying the password as
    otherwise it is included in the Nix store in plain text form. This can't be
    used alongside with **password**.

  :sha1pass:
    The null or string option corresponding to the CLI configuration option of
    the same name. The default is ``null``. Be aware that this includes this
    password in the Nix store in plain text form! Preferably use
    **sha1passFile**.

  :sha1passFile:
    The alternative way to specify **sha1pass** option. This is expected to be
    null or string with path to the file (on the NixOS machine) containing the
    SHA1 password to be used.

  :role:
    The list of strings corresponding to the CLI configuration option of the
    same name. The default is an empty list.

:config.role.<name>:
  The attribute set of the roles defined in the broker. The ``<name>`` is to be
  the role's name. The role has the following options:

  :access.<level>:
    The attribute set where names are one of ``bws``, ``rd``, ``wr``, ``cmd``,
    ``cfg``, ``srv``, ``ssrv``, ``dev``, and ``su``. The value is list of
    strings with SHV RPC RIs. This option corresponds to the ``role.*.access``
    CLI option.

  :mountPoints:
    The list of strings with SHV RPC RIs corresponding to the CLI configuration
    option of the same name. The default is empty list.

:config.autosetup:
  The list of automatic setup rules represented as modules with the following
  options:

  :deviceId:
    The list of strings corresponding to the CLI configuration option of the
    same name.

  :role:
    The string or list of strings corresponding to the CLI configuration option
    of the same name. The default is empty list.

  :mountPoint:
    The null or string option corresponding to the CLI configuration option of
    the same name. The default is null.

  :subscriptions:
    The list of strings corresponding to the CLI configuration option of the
    same name. The default is empty list.

:logLevel:
  The verbosity level of the service logging. This is one of the ``"CRITICAL"``,
  ``"FATAL"``, ``"ERROR"``, ``"WARN"``, ``"WARNING"``, ``"INFO"``, and
  ``"DEBUG"``. The default is ``"INFO"``.

:openFirewall:
  The boolean option enabling the automatic TCP ports opening. The default is
  ``false``.
