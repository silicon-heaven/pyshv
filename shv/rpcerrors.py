"""Implementation of Rpc RPC specific errors."""

from __future__ import annotations

import dataclasses
import enum


class RpcErrorCode(enum.IntEnum):
    """Number representing an SHV RPC error code."""

    NO_ERROR = 0
    INVALID_REQUEST = 1
    METHOD_NOT_FOUND = 2
    INVALID_PARAM = 3
    INTERNAL_ERR = 4
    PARSE_ERR = 5
    METHOD_CALL_TIMEOUT = 6
    METHOD_CALL_CANCELLED = 7
    METHOD_CALL_EXCEPTION = 8
    UNKNOWN = 9
    LOGIN_REQUIRED = 10
    USER_ID_REQUIRED = 11
    NOT_IMPLEMENTED = 12
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
    shv_error_map: dict[int, type[RpcError]] = dataclasses.field(default_factory=dict)

    def __new__(
        cls, msg: str | None = None, code: RpcErrorCode | None = None
    ) -> RpcError:
        """Create an appropriate exception based on the code."""
        ncls = cls.shv_error_map.get(cls.shv_error_code if code is None else code, cls)
        return super(RpcError, cls).__new__(ncls)  # noqa UP008

    def __init__(
        self, msg: str | None = None, code: RpcErrorCode | None = None
    ) -> None:
        super().__init__(msg, self.shv_error_code if code is None else code)

    @property
    def message(self) -> str | None:
        """Provides access to the SHV RPC message."""
        if not isinstance(self.args[0], str) and self.args[0] is not None:
            raise ValueError(f"Must be string or None but is: {type(self.args[0])}")
        return self.args[0]

    @property
    def error_code(self) -> RpcErrorCode:
        """Provides access to the :class:`RpcErrorCode`."""
        assert isinstance(self.args[1], RpcErrorCode)
        return self.args[1]


class RpcInvalidRequestError(RpcError):
    """The sent data are not valid request object."""

    shv_error_code = RpcErrorCode.INVALID_REQUEST


class RpcMethodNotFoundError(RpcError):
    """The method does not exist or is not available."""

    shv_error_code = RpcErrorCode.METHOD_NOT_FOUND


class RpcInvalidParamError(RpcError):
    """Invalid method parameter were provided."""

    shv_error_code = RpcErrorCode.INVALID_PARAM


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


class RpcLoginRequiredError(RpcError):
    """Login sequence must be performed before anything else."""

    shv_error_code = RpcErrorCode.LOGIN_REQUIRED


class RpcUserIDRequiredError(RpcError):
    """Request must be sent with UserID field."""

    shv_error_code = RpcErrorCode.USER_ID_REQUIRED


class RpcNotImplementedError(RpcError):
    """Called method that is not implemented right now but valid."""

    shv_error_code = RpcErrorCode.NOT_IMPLEMENTED


RpcError.shv_error_map = {
    e.shv_error_code: e
    for e in (
        RpcInvalidRequestError,
        RpcMethodNotFoundError,
        RpcInvalidParamError,
        RpcInternalError,
        RpcParseError,
        RpcMethodCallTimeoutError,
        RpcMethodCallCancelledError,
        RpcMethodCallExceptionError,
        RpcLoginRequiredError,
        RpcUserIDRequiredError,
        RpcNotImplementedError,
    )
}
