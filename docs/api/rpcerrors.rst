RPC Errors
==========

SHV RPC errors are optionally represented as native python Exceptions. Thus in
user code they can be handled with try-catch as any other exception. That
requires mapping of these errors to an appropriate Python :class:`Exception`
class.

There is a root exception for all SHV RPC errors :class:`shv.rpcdef.RpcError`
but that should be used only for errors without assigned code. There is a
dedicated children defined that should be preffered.

.. autoclass:: shv.rpcdef.RpcError

Standard errors
---------------

.. autoclass:: shv.rpcdef.RpcMethodNotFoundError
.. autoclass:: shv.rpcdef.RpcInvalidParamError
.. autoclass:: shv.rpcdef.RpcMethodCallExceptionError
.. autoclass:: shv.rpcdef.RpcLoginRequiredError
.. autoclass:: shv.rpcdef.RpcUserIDRequiredError
.. autoclass:: shv.rpcdef.RpcNotImplementedError
.. autoclass:: shv.rpcdef.RpcTryAgainLaterError
.. autoclass:: shv.rpcdef.RpcRequestInvalidError

Utilities
---------

.. autoclass:: shv.rpcdef.errors.RpcErrorCode
