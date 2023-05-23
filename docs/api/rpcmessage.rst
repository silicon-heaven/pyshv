API reference for RPC message
=============================

.. autoclass:: shv.RpcMessage


RPC method description types
----------------------------

These enums are used when listing methods.

.. autoclass:: shv.RpcMethodSignature
.. autoclass:: shv.RpcMethodFlags


RPC Errors as Python exceptions
-------------------------------

.. autoclass:: shv.RpcErrorCode
.. autoclass:: shv.RpcError
.. autoclass:: shv.RpcInternalError
.. autoclass:: shv.RpcInvalidParamsError
.. autoclass:: shv.RpcInvalidRequestError
.. autoclass:: shv.RpcMethodCallCancelledError
.. autoclass:: shv.RpcMethodCallExceptionError
.. autoclass:: shv.RpcMethodCallTimeoutError
.. autoclass:: shv.RpcMethodNotFoundError
.. autoclass:: shv.RpcParseError
