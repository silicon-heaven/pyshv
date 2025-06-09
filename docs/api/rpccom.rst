RPC communication
=================

Client
------

These are implementations if clients that connect to server or over some
connection to some other client.

.. autofunction:: shv.init_rpc_client
.. autofunction:: shv.connect_rpc_client
.. autoclass:: shv.RpcClient
.. autoclass:: shv.RpcClientTCP
.. autoclass:: shv.RpcClientUnix
.. autoclass:: shv.RpcClientPipe
.. autoclass:: shv.RpcClientTTY
.. autoclass:: shv.RpcClientWebSockets

Server
------

Servers are waiting for clients connection and provides you with client on the
sever side to communicate with newly connected peer.

.. autofunction:: shv.create_rpc_server
.. autoclass:: shv.RpcServer
.. autoclass:: shv.RpcServerTCP
.. autoclass:: shv.RpcServerUnix
.. autoclass:: shv.RpcServerTTY
.. autoclass:: shv.RpcServerWebSockets
.. autoclass:: shv.RpcServerWebSocketsUnix

Transport protocols
-------------------

SHV RPC is based on messages and these protocols are for sending these messages
over data stream. Please do not confuse this with :class:`shv.RpcProtocol`.

.. autoclass:: shv.RpcProtocolBlock
.. autoclass:: shv.RpcProtocolSerial
.. autoclass:: shv.RpcProtocolSerialCRC
.. autoclass:: shv.RpcTransportProtocol

Stream client and server bases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: shv.rpctransport.stream.RpcClientStream
.. autoclass:: shv.rpctransport.stream.RpcServerStream
