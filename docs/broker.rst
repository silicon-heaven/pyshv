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

  [rules.admin]
  level = su

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

  :rules: Space separated list of rules that this role assigns to the user.
  :roles: Space separated list of other roles. This allows combination of the
    roles and thus higher versatility in the way roles are structured. All rules
    from these roles are recursively considered to be part of the role
    specifying this option.

:rules.:
  Rules specify level of access for some specific method and path. These rules
  are assigned recursively to the path and the highest level always applies and
  thus you can't lower the access level if you grant higher one to the upper
  path. The allowed options are:

  :path: Path in the SHV node tree that this rules applies to and its children.
    The default is empty path and that is top level node.
  :method: Method name this rule applies to. There is no wild matching, the
    method name has to match exactly. The only exception is empty method name
    that matches any method. The default is empty method and this if you do not
    specify this option the rules applies to all methods.
  :level: Highest access level granted to the user having this rule in its
    roles. Note that we always use highest level from any rule that matches. We
    do not look for most exact rule.


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
To run the broker you have to await :meth:`shv.broker.RpcBroker.serve_forever`.
