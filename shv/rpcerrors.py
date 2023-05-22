"""Implementation of Rpc RPC specific errors."""
from __future__ import annotations

import enum
import typing


class RpcErrorCode(enum.IntEnum):
    """Number representing an SHV RPC error code."""

    NO_ERROR = 0
    INVALID_REQUEST = 1
    METHOD_NOT_FOUND = 2
    INVALID_PARAMS = 3
    INTERNAL_ERR = 4
    PARSE_ERR = 5
    METHOD_CALL_TIMEOUT = 6
    METHOD_CALL_CANCELLED = 7
    METHOD_CALL_EXCEPTION = 8
    UNKNOWN = 9
    USER_CODE = 32


class RpcError(RuntimeError):
    """Top level for Rpc RPC errors.

    This tries to be a bit smart when objects are created. There is class
    property `shv_error_map` that is used to lookup a more appropriate error
    object. If you are adding any of your own error codes you can add them to
    this map to be looked up by their code.

    :param msg: Message describing the error circumstances.
    :param code: Error code.
    """

    shv_error_code: RpcErrorCode = RpcErrorCode.UNKNOWN
    shv_error_map: dict[int, typing.Type[RpcError]] = {}

    def __new__(cls, msg: str, code: RpcErrorCode | None = None):
        ncls = cls.shv_error_map.get(cls.shv_error_code if code is None else code, cls)
        return super(RpcError, cls).__new__(ncls)

    def __init__(self, msg: str, code: RpcErrorCode | None = None):
        super().__init__(str(msg), self.shv_error_code if code is None else code)

    @property
    def message(self) -> str:
        """Provides access to the SHV RPC message."""
        return self.args[0]

    @property
    def error_code(self) -> RpcErrorCode:
        """Provides access to the :class:`RpcErrorCode`."""
        return self.args[1]


class RpcInvalidRequestError(RpcError):
    """The sent data are not valid request object."""

    shv_error_code = RpcErrorCode.INVALID_REQUEST


class RpcMethodNotFoundError(RpcError):
    """The method does not exist or is not available."""

    shv_error_code = RpcErrorCode.METHOD_NOT_FOUND


class RpcInvalidParamsError(RpcError):
    """Invalid method parameters were provided."""

    shv_error_code = RpcErrorCode.INVALID_PARAMS


class RpcInternalError(RpcError):
    """Internal JSON-RPC error."""

    shv_error_code = RpcErrorCode.INTERNAL_ERR


class RpcParseError(RpcError):
    """Invalid data were recived and were not possible to parse them."""

    shv_error_code = RpcErrorCode.PARSE_ERR


class RpcMethodCallTimeoutError(RpcError):
    """Method call timed out without providing result."""

    shv_error_code = RpcErrorCode.METHOD_CALL_TIMEOUT


class RpcMethodCallCancelledError(RpcError):
    """Method call was cancelled."""

    shv_error_code = RpcErrorCode.METHOD_CALL_CANCELLED


class RpcMethodCallExceptionError(RpcError):
    """Method call resulted in exception and not result."""

    shv_error_code = RpcErrorCode.METHOD_CALL_EXCEPTION


RpcError.shv_error_map = {
    e.shv_error_code: e
    for e in (
        RpcInvalidRequestError,
        RpcMethodNotFoundError,
        RpcInvalidParamsError,
        RpcInternalError,
        RpcParseError,
        RpcMethodCallTimeoutError,
        RpcMethodCallCancelledError,
        RpcMethodCallExceptionError,
    )
}
