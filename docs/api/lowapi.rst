Low level API
=============

This is the low level API implementing SHV RPC communication. The highler level
API is based on this one. This API provides API for exchanging SHV RPC messages.
This includes connection management between two peers as well as abstraction on
top of the message itself.

In  most cases you should use high level API but knowledge of this API is
beneficial because some actions are available only in it.

.. toctree::
   :maxdepth: 2

   rpccom
   rpcmessage
   rpcerrors
   rpcmethod
   rpcstdtypes
