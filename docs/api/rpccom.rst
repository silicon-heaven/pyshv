RPC communication
=================

Client
------

These are implementations if clients that connect to server or over some
connection to some other client.

.. autofunction:: shv.rpctransport.init_rpc_client
.. autofunction:: shv.rpctransport.connect_rpc_client
.. autoclass:: shv.rpctransport.RpcClient
.. autoclass:: shv.rpctransport.RpcClientTCP
.. autoclass:: shv.rpctransport.RpcClientUnix
.. autoclass:: shv.rpctransport.RpcClientPipe
.. autoclass:: shv.rpctransport.RpcClientTTY
.. autoclass:: shv.rpctransport.RpcClientWebSockets
.. autoclass:: shv.rpctransport.RpcClientCAN

Server
------

Servers are waiting for clients connection and provides you with client on the
sever side to communicate with newly connected peer.

.. autofunction:: shv.rpctransport.create_rpc_server
.. autoclass:: shv.rpctransport.RpcServer
.. autoclass:: shv.rpctransport.RpcServerTCP
.. autoclass:: shv.rpctransport.RpcServerUnix
.. autoclass:: shv.rpctransport.RpcServerTTY
.. autoclass:: shv.rpctransport.RpcServerWebSockets
.. autoclass:: shv.rpctransport.RpcServerWebSocketsUnix
.. autoclass:: shv.rpctransport.RpcServerCAN

Stream transport protocols
--------------------------

SHV RPC is based on messages and these protocols are for sending these messages
over data stream. Please do not confuse this with
:class:`shv.rpcurl.RpcProtocol`.

.. autoclass:: shv.rpctransport.RpcProtocolBlock
.. autoclass:: shv.rpctransport.RpcProtocolSerial
.. autoclass:: shv.rpctransport.RpcProtocolSerialCRC
.. autoclass:: shv.rpctransport.RpcTransportProtocol

Stream client and server bases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: shv.rpctransport.stream.RpcClientStream
.. autoclass:: shv.rpctransport.stream.RpcServerStream

CAN transport protocol
----------------------

The common CAN Bus access for multiple clients and servers.

.. autoclass:: shv.rpctransport.SHVCAN
