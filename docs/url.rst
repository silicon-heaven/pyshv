SHV RPC URL
===========

Unified Resource Locators are common way to specify connection. This is
definition of such URL for Silicon Heaven RPC.

Serialization of deserialization and abstraction on top of URL is provided by
:class:`shv.RpcUrl`.

Examples of URLs for Silicon Heaven RPC::

  tcp://user@localhost:3755?password=pass
  tcp://user@localhost:3755?password=pass&devid=42
  localsocket:/run/shvbroker.sock

The base format is::

  URL = scheme ":" ["//" authority] [path] ["?" options]

``options`` is sequence of attribute-value pairs split by ``=`` an
joined by ``&`` (example: ``password=test&devid=foo``). Supported
genral options are:

  :devid: Identify to the other side as device with this ID.
  :devmount: Identify to the other side as device and request mount to
    the given location.


**TCP/IP protocol**

  ::

    scheme = "tcp"
    authority = [username "@"] host [":" port]

  The default ``username`` is the local user name, ``host`` is
  ``localhost`` and ``port`` is ``3755``. ``path`` is ignored as it has
  no meaning in TCP/IP.

  The following additional ``options`` are supported for TCP/IP:

    :password: Plain text password used to login to the server.
    :shapass: Password hashed with SHA1 used to login to the server.


**Unix/Local domain socket**

  ::

    scheme = "localsocket"
    authority = root

  There is no default path and thus empty ``path`` is considered
  invalid. ``root`` is prefixed to the ``path`` if specified.
