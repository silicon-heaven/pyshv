:orphan:

'Named' helper
==============

The SHV RPC Broker configuration is designed in such a way that keys in mappings
are names and values contain additional options. For the purpose of working with
this configuration we pivot this to store the name in the object alongside with
other options, but at the same time it is beneficial to be able to access them
by name. This simple implementation provides exactly that.

.. autoclass:: shv.broker.config.NamedMap
.. autoclass:: shv.broker.config.NamedProtocol
.. autodata:: shv.broker.config.NamedT
