"""Implementation of Rpc RPC specific errors."""

from __future__ import annotations

import contextlib
import enum
import traceback
import typing

from .value import SHVType, is_shvimap


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
    TRY_AGAIN_LATER = 13
    REQUEST_INVALID = 14
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

    class Key(enum.IntEnum):
        """Keys in the error IMap."""

        CODE = 1
        MESSAGE = 2

    shv_error_code: typing.ClassVar[RpcErrorCode] = RpcErrorCode.UNKNOWN
    shv_error_map: typing.Final[dict[int, type[RpcError]]] = {}

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
        return typing.cast(str | None, self.args[0])

    @property
    def error_code(self) -> RpcErrorCode:
        """Provides access to the :class:`RpcErrorCode`."""
        return RpcErrorCode(self.args[1])

    def to_shv(self) -> SHVType:
        """Convert to SHV RPC representation."""
        res: dict[int, SHVType] = {
            self.Key.CODE: self.error_code,
            **({} if self.message is None else {self.Key.MESSAGE: self.message}),
        }
        return res

    @classmethod
    def from_shv(cls, value: SHVType) -> RpcError:
        """Create from SHV RPC representation."""
        if not is_shvimap(value):
            raise ValueError(f"Expected IMap but got {value!r}.")
        msg = value.get(cls.Key.MESSAGE)
        if not isinstance(msg, str | None):
            raise ValueError(f"Invalid Message format: {msg}")
        rcode = value.get(cls.Key.CODE)
        if not isinstance(rcode, int):
            raise ValueError(f"Invalid Code format: {rcode}")
        code = RpcErrorCode.UNKNOWN
        with contextlib.suppress(ValueError):
            code = RpcErrorCode(rcode)
        return cls(msg, code)

    @staticmethod
    def from_exception(exc: Exception) -> RpcError:
        """Create exception from other Python exception."""
        if isinstance(exc, RpcError):
            return exc
        return RpcMethodCallExceptionError("".join(traceback.format_exception(exc)))


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


class RpcTryAgainLaterError(RpcError):
    """The resource to fullfill request are temporally unavailable."""

    shv_error_code = RpcErrorCode.TRY_AGAIN_LATER


class RpcRequestInvalidError(RpcError):
    """There is no such known request (in response to abort request)."""

    shv_error_code = RpcErrorCode.REQUEST_INVALID
