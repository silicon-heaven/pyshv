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
locally for testing purposes with:

.. code-block:: console

   $ python3 -m shv.broker -c tests/broker/config.toml


The configuration file is in TOML format and in the minimal form can look like
this:

.. code-block:: toml

  [listen]
  internet = "tcp://[::]:3755"
  unix = "localsocket:shvbroker.sock"

  [users.admin]
  password = "admin"
  roles = ["admin"]

  [roles.admin]
  access = "ssrv"
  methods = [":"]

This configuration file specifies that broker should listen on all IP addresses
for TCP/IP connection on port 3755 and on local socket ``shvbroker.sock``. It
also declares one user that is admin and has super-service access level to all
methods on all nodes.

:name:
  The name of the broker. This is used when constructing ClientID to identify
  this broker. In default this is empty and thus only user's name is appended
  but if you specify it then user name will be prefixed with this name (forming
  ``localhost:foo`` for ``name = localhost`` and user ``foo``).

:listen:
  This table specifies URLs where server should listen for the new connections.
  The table keys are only informative and used for identification purpose (feel
  free to name them as ever you want).

:connect.*:
  These are tables that define connection to some other SHV broker. The ``*``
  must be the connection identifier name that is used only in logs but must be
  unique per connection. The following options needs to be specified in this
  table:

  :url: Where to connect including the login information.
  :user: User that connected client gets assigned to. This is user of this
    broker (not the remote one).

:users.*:
  These are sections that define different users. The ``*`` must be the user's
  name. The allowed options are:

  :password: Plain text password that is required to be provided by client
    when connecting to the broker. This allows user to use ``PLAIN`` and
    ``SHA1`` login methods. If you do not specify this option (nor ``sha1pass``)
    then this user won't be used for login but still can be used with
    ``connect.*.user``.
  :sha1pass: Password hashed with SHA1 hash that is required to be provided by
    client when connecting to the broker (note that ``password`` has precedence
    over this one). This allow user to use only ``SHA`` login method but has
    advantage that password is not stored in plain text on server.
  :roles: List of roles assigned to the user. These must be defined roles
    (``roles.*``).

:roles.*:
  Roles are groupings of rules that are assigned to the users. They provide
  versatility in the configuration. The ``*`` must be the role name. The allowed
  options are:

  :match: Specifies list of resource identifiers matching rules this role
    sets access level to. This can be up to triplet delimited with ``:``. The
    first field is pattern for SHV path, second field is method name and third
    is signal name. You can left out either signal or signal and method fields.
    The default for both signal and method fields is ``*`` (matching any name).
    The special exception is when you use empty string for method (such as
    ``PATH::SIGNAL``) and in such case it is assumed to be ``get``. The first
    field for path is glob pattern (rules from POSIX.2, 3.13 with added support
    for ``**``) and second and third fields are wildcard patterns (rules from
    POSIX.2, 3.13). Note that by specifying the ``PATH:METHOD:SIGNAL`` you also
    specify implicitly ``PATH:METHOD`` that is because signal access
    intrinsically provides access to the method itself.
  :access: Access level granted to the user with this role for methods and
    signals matching resource identifications in ``match``. Note that access
    level of the first role that has at least one matching rule is used. The
    ordering of the roles can be used to specify complex access rules. The
    following levels are allowed:
    :bws: The lowest level that commonly allows only nodes discovery.
    :rd: Allows reading basic property values as well as node discovery.
    :wr: Allows all that ``rd`` does plus changing basic property values.
    :cmd: Allows all that ``wr`` does plus command operations.
    :cfg: Allows all that ``cmd`` does plus configuration operations.
    :srv: Allows all that ``cfg`` does plus service operations.
    :ssrv: Allows all that ``srv`` with additional service operations.
    :dev: Allows pretty much all operations and is intended for developer
    access.
    :su: Super user access that allows everything.


The complete configuration example used in pySHV tests:

.. literalinclude:: ../tests/broker/config.toml
   :language: toml


Running directly from Python
----------------------------

It is also possible to run SHV Broker directly in Python code as part of your
Asyncio loop. The configuration can be created directly in the code without
having to write INI file through :class:`shv.broker.RpcBrokerConfig` but to
understand it please read the previous section describing the INI file format
configuration.

The configuration then can be used to initialize :class:`shv.broker.RpcBroker`.
To run the broker you have to await :meth:`shv.broker.RpcBroker.start_serving`.
