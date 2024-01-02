Using SHV RPC Broker
====================

Broker is available as one complete class that manages itself and all its
connections. In most cases it should be enough to just assemble the
configuration and running it.


Running in CLI
--------------

Broker can be started from console by issuing the following command:

.. code-block:: console

   $ pyshvbroker -c config.ini

If you do not have pySHV installed but only downloaded you can also run it
locally for testing purposes with:

.. code-block:: console

   $ python3 -m shv.broker -c config.ini


The configuration file is in INI format and in the minimal form can look like
this:

.. code-block:: ini

  [listen]
  internet = tcp://[::]:3755
  unix = localsocket:shvbroker.sock

  [users.admin]
  password = admin
  roles = admin

  [roles.admin]
  methods = :
  access = ssrv

This configuration file specifies that broker should listen on all IP addresses
for TCP/IP connection on port 3755 and on local socket ``shvbroker.sock``. It
also declares one user that is admin and has super-service access level.

:listen:
  This section specifies URLs where server should listen for the new
  connections. The option names are only informative and used for identification
  purpose (feel free to name them as ever you want).

:users.:
  These are sections that define different users. They all have to start with
  ``users.`` where the rest of the section name is the user's name. The allowed
  options are:

  :password: Plain text password that is required to be provided by client
    when connecting to the broker. This allows user to use ``PLAIN`` and
    ``SHA1`` login methods.
  :sha1pass: Password hashed with SHA1 hash that is required to be provided by
    client when connecting to the broker (note that ``password`` has precedence
    over this one). This allow user to use only ``SHA`` login method but has
    advantage that password is not stored in plain text on server.
  :roles: Space separated list of roles assigned to the user.

:roles.:
  Roles are groupings of rules that are assigned to the users. They provide
  versatility in the configuration. The role sections need to start with
  ``roles.`` and the rest of the section name is name of the role. The allowed
  options are:

  :methods: Specifies path and method this role applies on. The path and method
    is delimited with ``:`` and empty method matches all methods. And thus
    ``foo:`` matches all methods associated with node ``foo`` and its children.
    The sole ``:`` used in example matches all methods from root node and thus
    specifies the role to apply to all nodes and methods.
  :access: Access level granted to the user with this role for matching methods.
    Note that access level of the first role that has at least one matching rule
    is used. The ordering of the roles can be used to specify complex access
    rules. The following levels are allowed:
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
  :roles: Space separated list of other roles. This allows combination of the
    roles and thus higher versatility in the way roles are structured. All rules
    from these roles are considered to be part of the role specifying this
    option but checked after all top level ones were checked (BFS algorithm).


The complete configuration example used in pySHV tests:

.. literalinclude:: ../tests/broker/pyshvbroker.ini
   :language: ini


Running directly from Python
----------------------------

It is also possible to run SHV Broker directly in Python code as part of your
Asyncio loop. The configuration can be created directly in the code without
having to write INI file through :class:`shv.broker.RpcBrokerConfig` but to
understand it please read the previous section describing the INI file format
configuration.

The configuration then can be used to initialize :class:`shv.broker.RpcBroker`.
To run the broker you have to await :meth:`shv.broker.RpcBroker.start_serving`.
