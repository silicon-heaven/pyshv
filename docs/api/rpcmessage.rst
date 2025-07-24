RPC message abstraction
=======================

The RPC message is a container with meta assigned to it. It can contain a lot of
various options that are interpreted based on the rules defined in SHV standard.
The abstraction is provided to simplify working with this data structure while
you still can directly access the internal representation.

.. autoclass:: shv.rpcmessage.RpcMessage


Parameter parser helpers
------------------------

.. automodule:: shv.rpcparam
