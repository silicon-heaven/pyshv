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

  URL = scheme ":" ["//" [username "@"] authority] [path] ["?" options]

``options`` is sequence of attribute-value pairs split by ``=`` an joined by
``&`` (example: ``password=test&devid=foo``). Generally supported options are:

  :password: Plain text password used to login to the server.
  :shapass: Password hashed with SHA1 used to login to the server.
  :devid: Identify to the other side as device with this ID.
  :devmount: Identify to the other side as device and request mount to
    the given location.

The default ``username`` is the local user's name.


**TCP/IP protocol**

  ::

    scheme = "tcp"
    authority = host [":" port]

  The default ``host`` is ``localhost`` and ``port`` is ``3755``. Any non-empty
  ``path`` is invalid as it has no meaning in IP.


**Unix/Local domain socket**

  ::

    scheme = ("localsocket" | "unix")

  There is no default path and thus empty ``path`` is considered invalid.
  Any non-empty ``authority`` is also considered as invalid because it has no
  meaning.


**UDP/IP protocol**

  ::

    scheme = "udp"
    authority = host [":" port]

  The default ``host`` is ``localhost`` and ``port`` is ``3755``. Any non-empty
  ``path`` is invalid as it has no meaning in IP.


**RS232 / Serial protocol**

  ::

    scheme = ("serial" | "serialport" | "rs232")

  ``path`` needs to point to valit serial device. There is no default path and
  thus empty ``path`` is considered invalid. Any non-empty ``authority`` is
  also considered as invalid because it has no meaning.

  The additional supported options are:

  :baudrate: Specifies baudrate used for the serial communication.

  Other common serial-port parameters are at the moment not configurable and are
  expected to be: eight bits per word, no parity, single stop bit, enabled
  hardware flow control, disabled software flow control.
