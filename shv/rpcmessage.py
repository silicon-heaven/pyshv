"""Implementation of RpcMessage."""
from __future__ import annotations

import collections.abc
import enum
import typing

from .chainpack import ChainPackWriter
from .cpon import CponWriter
from .rpcerrors import RpcError, RpcErrorCode
from .rpcmethod import RpcMethodAccess
from .value import SHVIMap, SHVIMapType, SHVType, is_shvimap, shvmeta_eq


class RpcMessage:
    """Single SHV RPC message representation."""

    last_request_id: typing.ClassVar[int] = 0
    """Counter of request IDs to ensure that every request has unique ID."""

    @classmethod
    def next_request_id(cls) -> int:
        """Provide unique request identifier.

        The identifier won't repeat for this application as it is just simple
        counter that should never wrap.
        """
        cls.last_request_id += 1
        return cls.last_request_id

    def __init__(self, rpc_val: SHVIMapType | None = None) -> None:
        if rpc_val is None:
            rpc_val = SHVIMap()
        if not isinstance(rpc_val, SHVIMap):
            rpc_val = SHVIMap(rpc_val)
        self.value: SHVIMap = rpc_val

    def __eq__(self, other: typing.Any) -> bool:
        return isinstance(other, RpcMessage) and shvmeta_eq(self.value, other.value)

    def __repr__(self) -> str:
        return f"<RpcMessage {self.value.meta!r}: {self.value!r}>"

    class Tag(enum.IntEnum):
        """Tags in Meta for RPC message."""

        REQUEST_ID = 8
        PATH = 9
        METHOD = 10
        CALLER_IDS = 11
        ACCESS = 14

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
        return isinstance(self.value, SHVIMap)

    @property
    def is_request(self) -> bool:
        """Check if message is request."""
        return bool(self.has_request_id and self.has_method)

    @property
    def is_response(self) -> bool:
        """Check if message is a response."""
        return bool(self.has_request_id and not self.has_method)

    @property
    def is_error(self) -> bool:
        """Check if message is an error response."""
        return bool(
            self.is_response
            and self.error is not None
            and self.rpc_error.error_code != RpcErrorCode.NO_ERROR
        )

    @property
    def is_signal(self) -> bool:
        """Check if message is a signal."""
        return bool(not self.has_request_id and self.has_method)

    def make_response(self) -> RpcMessage:
        """Create new message that is response to this one."""
        if not self.is_request:
            raise ValueError("Response can be created from request only.")
        resp = RpcMessage()
        resp.request_id = self.request_id
        resp.caller_ids = self.caller_ids
        return resp

    @property
    def has_request_id(self) -> bool:
        """Check if valid request ID was provided in this message."""
        return self.Tag.REQUEST_ID in self.value.meta and isinstance(
            self.value.meta[self.Tag.REQUEST_ID], int
        )

    @property
    def request_id(self) -> int:
        """Request identificator of this message."""
        res = self.value.meta[self.Tag.REQUEST_ID]
        if not isinstance(res, int):
            raise ValueError(f"Invalid request ID type: {type(res)}")
        return res

    @request_id.setter
    def request_id(self, rqid: int | None) -> None:
        """Set given request identicator to this message."""
        if rqid is None:
            self.value.meta.pop(self.Tag.REQUEST_ID, None)
        else:
            self.value.meta[self.Tag.REQUEST_ID] = rqid

    @property
    def path(self) -> str:
        """SHV path specified for this message or empty string."""
        res = self.value.meta.get(self.Tag.PATH, "")
        if not isinstance(res, str):
            raise ValueError(f"Invalid path type: {type(res)}")
        return res

    @path.setter
    def path(self, path: str) -> None:
        """Set given path as SHV path for this message."""
        if path:
            self.value.meta[self.Tag.PATH] = path
        else:
            self.value.meta.pop(self.Tag.PATH, None)

    @property
    def has_method(self) -> bool:
        """Check if valid method name was provided in this message."""
        return self.Tag.METHOD in self.value.meta and isinstance(
            self.value.meta[self.Tag.METHOD], str
        )

    @property
    def method(self) -> str:
        """SHV method name for this message."""
        res = self.value.meta[self.Tag.METHOD]
        if not isinstance(res, str):
            raise ValueError(f"Invalid method type: {type(res)}")
        return res

    @method.setter
    def method(self, method: str) -> None:
        """Set SHV method name for this message."""
        if method:
            self.value.meta[self.Tag.METHOD] = method
        else:
            self.value.meta.pop(self.Tag.METHOD, None)

    @property
    def caller_ids(self) -> collections.abc.Sequence[int]:
        """Caller idenfieiers associated with this message."""
        res = self.value.meta.get(self.Tag.CALLER_IDS, None)
        if isinstance(res, int):
            return [res]
        if not isinstance(res, list):
            return []
        filter(lambda v: isinstance(v, int), res)
        return res

    @caller_ids.setter
    def caller_ids(self, cids: collections.abc.Sequence[int]) -> None:
        """Set caller idenfieiers associated with this message."""
        if not cids:
            self.value.meta.pop(self.Tag.CALLER_IDS, None)
        else:
            some: SHVType = cids
            if len(cids) == 1:
                some = cids[0]
            self.value.meta[self.Tag.CALLER_IDS] = some

    @property
    def access(self) -> collections.abc.Sequence[str]:
        """Granted access sequence."""
        res = self.value.meta.get(self.Tag.ACCESS, "")
        if isinstance(res, str):
            if res:
                return res.split(",")
        return []

    @access.setter
    def access(self, access: collections.abc.Sequence[str]) -> None:
        """Set granted access sequence."""
        if access:
            self.value.meta[self.Tag.ACCESS] = access
        else:
            self.value.meta.pop(self.Tag.ACCESS, None)

    @property
    def rpc_access(self) -> RpcMethodAccess | None:
        """Access level as :class:`shv.RpcMethodAccess`."""
        m = RpcMethodAccess.strmap()
        for access in self.access:
            if access in m:
                return m[access]
        return None

    @rpc_access.setter
    def rpc_access(self, access: RpcMethodAccess | None) -> None:
        """Set access level with :class:`shv.RpcMethodAccess`."""
        if access is not None:
            self.value.meta[self.Tag.ACCESS] = RpcMethodAccess.tostr(access)
        else:
            self.value.meta.pop(self.Tag.ACCESS, None)

    @property
    def param(self) -> SHVType:
        """SHV parameters for the method call."""
        return self.value.get(self.Key.PARAMS, None) if is_shvimap(self.value) else None

    @param.setter
    def param(self, param: SHVType) -> None:
        """Set SHV parameters for this method call."""
        if param is None:
            self.value.pop(self.Key.PARAMS, None)
        else:
            self.value[self.Key.PARAMS] = param

    @property
    def result(self) -> SHVType:
        """SHV method call result."""
        return self.value.get(self.Key.RESULT, None) if is_shvimap(self.value) else None

    @result.setter
    def result(self, result: SHVType) -> None:
        """Set SHV method call result."""
        if result is None:
            self.value.pop(self.Key.RESULT, None)
        else:
            self.value[self.Key.RESULT] = result

    @property
    def error(self) -> SHVType:
        """SHV method call error."""
        return self.value.get(self.Key.ERROR, None) if is_shvimap(self.value) else None

    @error.setter
    def error(self, error: SHVType) -> None:
        """Set SHV method call error."""
        if error is None:
            self.value.pop(self.Key.ERROR, None)
        else:
            self.value[self.Key.ERROR] = error

    @property
    def rpc_error(self) -> RpcError:
        """SHV method call error in standard SHV format :class:`RpcError`."""
        res = self.error
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
            return RpcError(msg, code)
        return RpcError(res if isinstance(res, str) else "", RpcErrorCode.UNKNOWN)

    @rpc_error.setter
    def rpc_error(self, error: RpcError) -> None:
        """Set SHV method call error in standard SHV format."""
        if error.error_code == RpcErrorCode.NO_ERROR:
            self.error = None
        else:
            err: SHVIMapType = {
                self.ErrorKey.CODE: error.error_code,
                self.ErrorKey.MESSAGE: error.message,
            }
            self.error = err

    def to_string(self) -> str:
        """Convert message to CPON and return it as string."""
        return self.to_cpon().decode("utf-8")

    def to_cpon(self) -> bytes:
        """Convert message to Cpon."""
        return CponWriter.pack(self.value) if self.is_valid() else b""

    def to_chainpack(self) -> bytes:
        """Convert message to Chainpack."""
        return ChainPackWriter.pack(self.value) if self.is_valid() else b""

    @classmethod
    def request(
        cls,
        path: str,
        method: str,
        param: SHVType = None,
        rid: int | None = None,
    ) -> "RpcMessage":
        """Create request message.

        :param path: SHV path for signal.
        :param method: method name for signal.
        :param param: Parameters passed to the method.
        :param rid: Request identifier for this message. It is automatically assigned if
          ``None`` is passed.
        """
        res = cls()
        res.request_id = rid or cls.next_request_id()
        res.method = method
        res.path = path
        res.param = param
        return res

    @classmethod
    def signal(
        cls,
        path: str,
        method: str,
        value: SHVType = None,
        access: RpcMethodAccess = RpcMethodAccess.READ,
    ) -> "RpcMessage":
        """Create signal message.

        :param path: SHV path for signal.
        :param method: method name for signal.
        :param value: Value to be sent in the message.
        :param access: Minimal access level needed to get this signal.
        """
        res = cls()
        res.method = method
        res.path = path
        res.param = value
        res.rpc_access = access
        return res

    @classmethod
    def chng(cls, path: str, value: SHVType) -> "RpcMessage":
        """Create message for ``chng`` signal.

        :param path: SHV path for signal.
        :param value: New value to be sent in the message.
        """
        return cls.signal(path, "chng", value)
