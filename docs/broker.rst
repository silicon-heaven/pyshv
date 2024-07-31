Using SHV RPC Broker
====================

Broker is available as one complete class that manages itself and all its
connections. In most cases it should be enough to just assemble the
configuration and running it.


Running in CLI
--------------

Broker can be started from console by issuing the following command:

.. code-block:: console

   $ pyshvbroker -c config.toml

If you do not have pySHV installed but only downloaded you can also run it
locally (from pySHV source directory) for testing purposes with:

.. code-block:: console

   $ python3 -m shv.broker -c tests/broker/config.toml


The configuration file is in TOML format and in the minimal form can look like
this:

.. code-block:: toml

  listen = ["tcp://[::]:3755", "localsocket:shvbroker.sock"]

  [users.admin]
  password = "admin"
  role = "admin"

  [role.admin]
  access.ssrv = "**"

This configuration file specifies that broker should listen on all IP addresses
for TCP/IP connection on port 3755 and on local socket ``shvbroker.sock``. It
also declares one user that is admin and has super-service access level to all
methods on all nodes.

The following are all available keys for top-level table in TOML:

:name:
  The name of the broker. This is used when constructing ClientID to identify
  this broker. In default this is empty and thus only user's name is appended
  but if you specify it then user name will be prefixed with this name (forming
  ``localhost:foo`` for ``name = localhost`` and user ``foo``).

:listen:
  This array that specifies string URLs where server should listen for the new
  connections. It is allowed to specify single URL string directly without using
  array.

:connect:
  This is array of tables that defines connections to some other SHV broker. The
  tables have the following keys:

  :url: URL used for the connection. It is connection host as well as
    authentication info or remote mount point.
  :role: The role name (or array of role names) to be used to control access of
    the connected peer on this broker.
  :mountPoint: Optional local mount point for the connected peer.
  :subscriptions: The array of subscriptions in `resource identifier
    <https://silicon-heaven.github.io/shv-doc/rpcri.html>`_ format used
    as an initial set of subscriptions this connection gets assigned.

:user.*:
  These are tables that define different users. The ``*`` stands for user's name
  that must be unique. The allowed options are:

  :password: Plain text password that is required to be provided by client
    when connecting to the broker. This allows user to use ``PLAIN`` and
    ``SHA1`` login methods.
  :sha1pass: Password hashed with SHA1 hash that is required to be provided by
    client when connecting to the broker (note that ``password`` has precedence
    over this one). This allow user to use ``PLAIN`` and ``SHA1`` login method
    and has advantage that password is not stored in plain text on server.
  :role: Role name (or array of role names) assigned to the user. They are used
    to control access of the peer on this broker, limit mount points requested
    by user and is used in autosetup selection. If not specified ``default`` is
    used.

:role.*:
  These are tables that define different roles. The ``*`` stands for role's name
  that must be unique and is referenced by ``user.*.role`` and
  ``connect[].role``. It is used to control access to the methods and signals as
  well as to limit mount points user can request. The allowed options are:

  :access: This is table with access levels as keys and `resource
    identifiers for methods
    <https://silicon-heaven.github.io/shv-doc/rpcri.html>`_ in array as
    value. The highest access level that has matching resource identifier is
    used. The following `access levels
    <https://silicon-heaven.github.io/shv-doc/shvrpcconcepts.html#access-control>`_
    from highest to the lowest are supported:

    - ``su`` Admin
    - ``dev`` Development
    - ``ssrv`` Super-service
    - ``srv`` Service
    - ``cfg`` Config
    - ``cmd`` Command
    - ``wr`` Write
    - ``rd`` Read
    - ``bws`` Browse

  :mountPoints: Is wildcard pattern (rules from POSIX.2, 3.13) or array of them
    that limits mount points user can request during login (option
    ``device.mountPoint``). If no role that user specifies has this option then
    explicit mount point is not allowed. Note that this doesn't limit mount
    point assigned by ``autosetup`` nor ``connect[].mountPoint``.

:autosetup:
  This must be an array of tables that specify rules for the automatic clients
  setup for logged in users. This includes mounting and initial subscriptions
  setup. The order of the array is important because the first one that matches
  roles and device ID is used. No initial setup is applied if none matches. The
  tables supports the following fields:

  :deviceId: This is wildcard pattern (rules from POSIX.2, 3.13) or array of
    them for device ID that client must supply in login option
    ``device.deviceId`` to be considered for this setup.
  :roles: The array with role names that must be assigned to the user to be
    considered for this setup. If not specified then all roles are considered.
  :mountPoint: The printf-like format string to generate mount point client will
    be automatically mounted to. This is used only if client did not specify its
    own mount point with login option ``device.mountPoint``. The format string
    can contain the following stand-ins:

    - ``%d`` device ID used by device.
    - ``%r`` the role user has assigned.
    - ``%u`` the user's name for user used to login to the Broker.
    - ``%i`` unique number that in default is replaced with empty string but if
      mount point already exists then it is number from ``1`` to get a unique
      mount point.
    - ``%I`` unique number from ``0`` to deduce a unique mount point. Contrary
      to the ``%i`` it is never expanded to empty string but otherwise it is
      same.
    - ``%%`` the plain ``%``.

  :subscriptions: The array of subscriptions in `resource identifier
    <https://silicon-heaven.github.io/shv-doc/rpcri.html>`_ format used
    as an initial set of subscriptions user gets assigned.

The complete configuration example used in pySHV tests:

.. literalinclude:: ../tests/broker/config.toml
   :language: toml

The second example that is used to test sub-broker:

.. literalinclude:: ../tests/broker/subconfig.toml
   :language: toml


Running directly from Python
----------------------------

It is also possible to run SHV Broker directly in Python code as part of your
Asyncio loop. The configuration can be created directly in the code without
having to write TOML file through :class:`shv.broker.RpcBrokerConfig` but to
understand it please read the previous section describing the TOML file format
configuration. You can also create your custom configuration based on the
:class:`shv.broker.RpcBrokerConfigABC` which might be in some cases easier.

The configuration then can be used to initialize :class:`shv.broker.RpcBroker`.
To run the broker you have to await :meth:`shv.broker.RpcBroker.start_serving`.

It is also possible to extend the broker implementation to add custom nodes.
To do so you need to extend :class:`shv.broker.RpcBroker` and include extension
of :class:`shv.broker.RpcBroker.Client`,
:class:`shv.broker.RpcBroker.LoginClient`, and
:class:`shv.broker.RpcBroker.ConnectClient`. The minimal viable overload is:

.. code-block:: python

   from shv.broker import RpcBroker

   class MyBroker(RpcBroker):

       class Client(RpcBroker.Client):
           pass  # Feel free extend this client as you would for SHV device

       class LoginClient(RpcBroker.LoginClient, MyBroker.Client):
          pass  # To inject extended client into login clients.

       class ConnectClient(RpcBroker.LoginClient, MyBroker.Client):
          pass  # To inject extended client into connecting clients.
