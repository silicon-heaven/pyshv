"""Implementation of RpcMessage."""
from __future__ import annotations

import collections.abc
import enum

from .chainpack import ChainPackWriter
from .cpon import CponWriter
from .rpcerrors import RpcError, RpcErrorCode
from .value import SHVDict, SHVMeta, SHVType, is_shvimap, is_shvmap, shvmeta


class RpcMessage:
    """Single SHV RPC message representation."""

    def __init__(self, rpc_val=None):
        self.value = SHVMeta.new({}, {}) if rpc_val is None else rpc_val

    class Tag(enum.IntEnum):
        """Tags in Meta for RPC message."""

        REQUEST_ID = 8
        SHVPATH = 9
        METHOD = 10
        CALLER_IDS = 11

    class Key(enum.IntEnum):
        """Keys in the toplevel IMap of the RPC message."""

        PARAMS = 1
        RESULT = 2
        ERROR = 3

    class ErrorKey(enum.IntEnum):
        """Keys in the error IMap."""

        CODE = 1
        MESSAGE = 2

    def is_valid(self) -> bool:
        """Check if message is valid RPC message."""
        # TODO maybe do more work than just check basic type
        return isinstance(self.value, SHVDict)

    def is_request(self):
        """Check if message is request."""
        return self.request_id() and self.method()

    def is_response(self):
        """Check if message is a response."""
        return self.request_id() and not self.method()

    def is_error(self):
        """Check if message is an error response."""
        return (
            self.is_response()
            and self.error() is not None
            and self.shverror()[0] != RpcErrorCode.NO_ERROR
        )

    def is_signal(self):
        """Check if message is a signal."""
        return not self.request_id() and self.method()

    def make_response(self) -> RpcMessage:
        if not self.is_request():
            raise ValueError("Response can be created from request only.")
        resp = RpcMessage()
        resp.set_request_id(self.request_id())
        resp.set_caller_ids(self.caller_ids())
        return resp

    def request_id(self) -> int | None:
        """Request identificator of this message."""
        res = shvmeta(self.value).get(self.Tag.REQUEST_ID, None)
        return res if isinstance(res, int) else None

    def set_request_id(self, rqid: int | None) -> None:
        """Set given request idenficator to this message."""
        if rqid is None:
            shvmeta(self.value).pop(self.Tag.REQUEST_ID, None)
        else:
            self.value = SHVMeta.new(self.value, {self.Tag.REQUEST_ID: rqid})

    def shv_path(self) -> str | None:
        """SHV path specified for this message."""
        res = shvmeta(self.value).get(self.Tag.SHVPATH, None)
        return res if isinstance(res, str) else None

    def set_shv_path(self, path: str | None) -> None:
        """Set given path as SHV path for this message."""
        if path is None:
            shvmeta(self.value).pop(self.Tag.SHVPATH, None)
        else:
            self.value = SHVMeta.new(self.value, {self.Tag.SHVPATH: path})

    def caller_ids(self) -> collections.abc.Sequence[int] | None:
        """Caller idenfieiers associated with this message."""
        res = shvmeta(self.value).get(self.Tag.CALLER_IDS, None)
        if isinstance(res, int):
            return [res]
        if not isinstance(res, list):
            return None
        filter(lambda v: isinstance(v, int), res)
        return res  # type: ignore

    def set_caller_ids(self, cids: collections.abc.Sequence[int] | None) -> None:
        """Set caller idenfieiers associated with this message."""
        if not cids:
            shvmeta(self.value).pop(self.Tag.CALLER_IDS, None)
        else:
            some: SHVType = cids
            self.value = SHVMeta.new(self.value, {self.Tag.CALLER_IDS: some})

    def method(self) -> str | None:
        """SHV method name for this message."""
        res = shvmeta(self.value).get(self.Tag.METHOD, None)
        return res if isinstance(res, str) else None

    def set_method(self, method: str) -> None:
        """Set SHV method name for this message."""
        if method is None:
            shvmeta(self.value).pop(self.Tag.METHOD, None)
        else:
            self.value = SHVMeta.new(self.value, {self.Tag.METHOD: method})

    def params(self) -> SHVType:
        """SHV parameters for the method call."""
        return self.value.get(self.Key.PARAMS, None) if is_shvimap(self.value) else None

    def set_params(self, params: SHVType) -> None:
        """Set SHV parameters for this method call."""
        if params is None:
            self.value.pop(self.Key.PARAMS, None)
        else:
            self.value[self.Key.PARAMS] = params

    def result(self) -> SHVType:
        """SHV method call result."""
        return self.value.get(self.Key.RESULT, None) if is_shvimap(self.value) else None

    def set_result(self, result: SHVType) -> None:
        """Set SHV method call result."""
        if result is None:
            self.value.pop(self.Key.RESULT, None)
        else:
            self.value[self.Key.RESULT] = result

    def error(self) -> SHVType:
        """SHV method call error."""
        return self.value.get(self.Key.ERROR, None) if is_shvimap(self.value) else None

    def set_error(self, error: SHVType) -> None:
        """Set SHV method call error."""
        if error is None:
            self.value.pop(self.Key.ERROR, None)
        else:
            self.value[self.Key.ERROR] = error

    def shverror(self) -> tuple[RpcErrorCode, str]:
        """SHV method call error in standard SHV format."""
        res = self.error()
        if is_shvimap(res):
            assert isinstance(res, dict)
            rcode = res.get(self.ErrorKey.CODE)
            code: RpcErrorCode = RpcErrorCode.UNKNOWN
            if isinstance(rcode, int):
                try:
                    code = RpcErrorCode(rcode)
                except ValueError:
                    pass
            rmsg = res.get(self.ErrorKey.MESSAGE)
            msg = rmsg if isinstance(rmsg, str) else ""
            return code, msg
        return RpcErrorCode.UNKNOWN, res if isinstance(res, str) else ""

    def set_shverror(self, code: RpcErrorCode, msg: str = ""):
        """Set SHV method call error in standard SHV format."""
        self.set_error({self.ErrorKey.CODE: code, self.ErrorKey.MESSAGE: msg})

    def rpc_error(self) -> RpcError | None:
        """Get SHV RPC error as RpcError."""
        if not self.is_error():
            return None
        code, msg = self.shverror()
        return RpcError(msg, code)

    def set_rpc_error(self, error: RpcError) -> None:
        """Set given SHV RPC error to this message."""
        self.set_shverror(error.error_code, error.message)

    def to_string(self) -> str:
        """Convert message to CPON and return it as string."""
        return self.to_cpon().decode("utf-8")

    def to_cpon(self) -> bytes:
        """Convert message to Cpon."""
        return CponWriter.pack(self.value) if self.is_valid() else b""

    def to_chainpack(self) -> bytes:
        """Convert message to Chainpack."""
        return ChainPackWriter.pack(self.value) if self.is_valid() else b""
