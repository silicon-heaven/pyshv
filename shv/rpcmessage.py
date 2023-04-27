from __future__ import annotations

import enum

from .rpcerrors import RpcError, RpcErrorCode
from .chainpack import ChainPackWriter
from .cpon import CponWriter
from .rpcvalue import RpcValue


class RpcMessage:
    """Single SHV RPC message representation."""

    def __init__(self, rpc_val=None):
        if rpc_val is None:
            self.rpcValue = RpcValue()
        elif isinstance(rpc_val, RpcValue):
            self.rpcValue = rpc_val
        else:
            raise TypeError("RpcMessage cannot be constructed with: " + type(rpc_val))
        self.rpcValue.set(
            self.rpcValue.value if self.rpcValue.value else {},
            self.rpcValue.meta if self.rpcValue.meta else {},
            RpcValue.Type.IMap,
        )

    class Tag(enum.IntEnum):
        REQUEST_ID = 8
        SHVPATH = 9
        METHOD = 10
        CALLER_IDS = 11

    class Key(enum.IntEnum):
        PARAMS = 1
        RESULT = 2
        ERROR = 3
        ERROR_CODE = 1
        ERROR_MESSAGE = 2

    def is_valid(self):
        """Check if message is valid RPC message."""
        return bool(isinstance(self.rpcValue, RpcValue))

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

    def make_response(self):
        if not self.is_request():
            raise ValueError("Response can be created from request only.")
        resp = RpcMessage()
        resp.set_request_id(self.request_id())
        resp.set_caller_ids(self.caller_ids())
        return resp

    def request_id(self):
        return self.rpcValue.meta.get(self.Tag.REQUEST_ID) if self.is_valid() else None

    def set_request_id(self, rqid):
        self.rpcValue.meta[self.Tag.REQUEST_ID] = rqid

    def shv_path(self):
        return self.rpcValue.meta.get(self.Tag.SHVPATH) if self.is_valid() else None

    def set_shv_path(self, val):
        if val is None:
            self.rpcValue.meta.pop(self.Tag.SHVPATH, None)
        else:
            self.rpcValue.meta[self.Tag.SHVPATH] = val

    def caller_ids(self):
        return self.rpcValue.meta.get(self.Tag.CALLER_IDS) if self.is_valid() else None

    def set_caller_ids(self, val):
        if val is None:
            self.rpcValue.meta.pop(self.Tag.CALLER_IDS, None)
        else:
            self.rpcValue.meta[self.Tag.CALLER_IDS] = val

    def method(self):
        return self.rpcValue.meta.get(self.Tag.METHOD) if self.is_valid() else None

    def set_method(self, val):
        if val is None:
            self.rpcValue.meta.pop(self.Tag.METHOD, None)
        else:
            self.rpcValue.meta[self.Tag.METHOD] = val

    def params(self):
        return self.rpcValue.value.get(self.Key.PARAMS) if self.is_valid() else None

    def set_params(self, params):
        if params is None:
            self.rpcValue.value.pop(self.Key.PARAMS, None)
        else:
            self.rpcValue.value[self.Key.PARAMS] = params

    def result(self):
        return self.rpcValue.value.get(self.Key.RESULT) if self.is_valid() else None

    def set_result(self, result):
        if result is None:
            self.rpcValue.value.pop(self.Key.RESULT, None)
        else:
            self.rpcValue.value[self.Key.RESULT] = result

    def error(self):
        return self.rpcValue.value.get(self.Key.ERROR) if self.is_valid() else None

    def set_error(self, err):
        if err is None:
            self.rpcValue.value.pop(self.Key.ERROR, None)
        else:
            self.rpcValue.value[self.Key.ERROR] = err

    def shverror(self) -> tuple[RpcErrorCode, str]:
        res = self.error()
        if res is not None and res.type == RpcValue.Type.Map:
            return res.value.get(self.Key.ERROR_CODE), res.value.get(
                self.Key.ERROR_MESSAGE
            )
        return RpcErrorCode.UNKNOWN, res

    def set_shverror(self, code: RpcErrorCode, msg: str = ""):
        self.set_error({self.Key.ERROR_CODE: code, self.Key.ERROR_MESSAGE: msg})

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
        return self.to_cpon().decode()

    def to_cpon(self) -> bytes:
        """Convert message to Cpon."""
        return CponWriter.pack(self.rpcValue) if self.is_valid() else b""

    def to_chainpack(self) -> bytes:
        """Convert message to Chainpack."""
        return ChainPackWriter.pack(self.rpcValue) if self.is_valid() else b""
