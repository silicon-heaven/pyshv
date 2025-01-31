RPC Errors
==========

SHV RPC errors are optionally represented as native python Exceptions. Thus in
user code they can be handled with try-catch as any other exception. That
requires mapping of these errors to an appropriate Python :class:`Exception`
class.

There is a root exception for all SHV RPC errors :class:`shv.RpcError` but that
should be used only for errors without assigned code. There is a dedicated
children defined that should be preffered.

.. autoclass:: shv.RpcError

Standard errors
---------------

.. autoclass:: shv.RpcMethodNotFoundError
.. autoclass:: shv.RpcInvalidParamError
.. autoclass:: shv.RpcMethodCallExceptionError
.. autoclass:: shv.RpcLoginRequiredError
.. autoclass:: shv.RpcUserIDRequiredError
.. autoclass:: shv.RpcNotImplementedError

Utilities
---------

.. autoclass:: shv.RpcErrorCode
