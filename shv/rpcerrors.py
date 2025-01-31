"""Implementation of Rpc RPC specific errors."""

from __future__ import annotations

import enum
import typing


class RpcErrorCode(enum.IntEnum):
    """Number representing an SHV RPC error code."""

    NO_ERROR = 0
    METHOD_NOT_FOUND = 2
    INVALID_PARAM = 3
    METHOD_CALL_EXCEPTION = 8
    UNKNOWN = 9
    LOGIN_REQUIRED = 10
    USER_ID_REQUIRED = 11
    NOT_IMPLEMENTED = 12
    USER_CODE = 32


class RpcError(RuntimeError):
    """Top level for Rpc RPC errors.

    This tries to be a bit smart when objects are created. The
    :attr:`shv_error_map` is used to lookup a more appropriate error object.
    If you are adding any of your own error codes you can add them to this map
    to be looked up by their code.

    :param msg: Message describing the error circumstances.
    :param code: Error code.
    """

    shv_error_code: typing.ClassVar[RpcErrorCode] = RpcErrorCode.UNKNOWN
    shv_error_map: typing.ClassVar[dict[int, type[RpcError]]] = {}

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

    def __init_subclass__(cls, *args: typing.Any, **kwargs: typing.Any) -> None:  # noqa: ANN401
        super().__init_subclass__(*args, **kwargs)
        if cls.shv_error_code in RpcError.shv_error_map:
            raise TypeError(f"RPC Error already defined for {cls.shv_error_code}")
        RpcError.shv_error_map[cls.shv_error_code] = cls

    @property
    def message(self) -> str | None:
        """Provides access to the SHV RPC message."""
        if not isinstance(self.args[0], str) and self.args[0] is not None:
            raise ValueError(f"Must be string or None but is: {type(self.args[0])}")
        return self.args[0]

    @property
    def error_code(self) -> RpcErrorCode:
        """Provides access to the :class:`RpcErrorCode`."""
        return RpcErrorCode(self.args[1])


class RpcMethodNotFoundError(RpcError):
    """The method does not exist or is not available."""

    shv_error_code = RpcErrorCode.METHOD_NOT_FOUND


class RpcInvalidParamError(RpcError):
    """Invalid method parameter were provided."""

    shv_error_code = RpcErrorCode.INVALID_PARAM


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
