Broker configuration API
========================

The SHV RPC Broker configuration is split to two parts. One is the generic API
that you can use to implement your own custom configuration and the other is the
real implementation reading the TOML configuration file format.


Standard configuration
----------------------

This is standard in the meaning of configuration defined and described for
`pyshvbroker` but not in terms of SHV standard!

.. autoclass:: shv.broker.RpcBrokerConfig
.. autoclass:: shv.broker.RpcBrokerConfigurationError


Generic Configuration
---------------------

.. autoclass:: shv.broker.RpcBrokerConfigABC
.. autoclass:: shv.broker.RpcBrokerRoleABC
