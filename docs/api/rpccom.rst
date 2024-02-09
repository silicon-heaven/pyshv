RPC communication
=================

URL and connection parameters
-----------------------------

.. autoclass:: shv.RpcUrl
.. autoclass:: shv.RpcProtocol
.. autoclass:: shv.RpcLogin
.. autoclass:: shv.RpcLoginType

Client
------

These are implementations if clients that connect to server or over some
connection to some other client.

.. automethod:: shv.init_rpc_client
.. automethod:: shv.connect_rpc_client
.. autoclass:: shv.RpcClient
.. autoclass:: shv.RpcClientTCP
.. autoclass:: shv.RpcClientUnix
.. autoclass:: shv.RpcClientPipe
.. autoclass:: shv.RpcClientTTY

Server
------

Servers are waiting for clients connection and provides you with client on the
sever side to communicate with newly connected peer.

.. automethod:: shv.rpcserver.create_rpc_server
.. autoclass:: shv.RpcServer
.. autoclass:: shv.RpcServerTCP
.. autoclass:: shv.RpcServerUnix
.. autoclass:: shv.RpcServerTTY

Transport protocols
-------------------

SHV RPC is based on messages and these protocols are for sending these messages
over data stream. Please do not confuse this with :class:`shv.RpcProtocol`.

.. autoclass:: shv.RpcProtocolStream
.. autoclass:: shv.RpcProtocolSerial
.. autoclass:: shv.RpcProtocolSerialCRC
.. autoclass:: shv.RpcTransportProtocol
