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
  rules = admin
  access = su

  [rules.admin]

This configuration file specifies that broker should listen on all IP addresses
for TCP/IP connection on port 3755 and on local socket ``shvbroker.sock``. It
also declares one user that is admin and has highest access level.

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

  :access: Access level granted to the user with this role. Note that access
    level of the first role that has at least one matching rule is used. The
    ordering of the roles can be used to specify complex access rules.
  :rules: Space separated list of rules that are checked to find out if this
    role applies.
  :roles: Space separated list of other roles. This allows combination of the
    roles and thus higher versatility in the way roles are structured. All rules
    from these roles are considered to be part of the role specifying this
    option but checked after all top level ones were checked (BFS algorithm).

:rules.:
  Rules provide simple matching of path and methods and are used to determine if
  role applies to some specific SHV RPC request.

  :path: Path in the SHV node tree that this rules applies to and its children.
    The default is empty path and that is top level node.
  :methods: Space separated list if names this rule applies to. There is no wild
    matching, the method name has to match exactly. Empty list is considered to
    match all methods. The default is empty list and thus if you do not specify
    this option the rules applies to all methods on matching path.


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
