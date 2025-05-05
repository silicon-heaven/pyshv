"""Implementation of RpcMessage."""

from __future__ import annotations

import collections.abc
import enum
import time
import typing

from .chainpack import ChainPackWriter
from .cpon import CponWriter
from .path import SHVPath
from .rpcaccess import RpcAccess
from .rpcerrors import RpcError, RpcErrorCode
from .value import (
    SHVIMap,
    SHVType,
    is_shvlist,
    shvmeta_eq,
)


class RpcMessage:
    """Single SHV RPC message representation.

    :param rpc_val: The value of the received and unpacked SHV RPC message or
      ``None`` in case you want to create a new message instead.
    """

    _last_request_id: typing.ClassVar[int] = 0
    _last_request_id_rollover: typing.ClassVar[float] = time.monotonic()

    @classmethod
    def next_request_id(cls) -> int:
        """Provide unique request identifier.

        The identifier won't repeat for this application in a reasonable time as
        it is just simple counter that wrap after a long time.

        In most cases we could get away with not wrapping the counter at all
        because it is unlikely that we would run out of common implementation
        limit of 64 bits (this is limit in other implementations not Python).
        But further messages would be increased in size. Instead we choose to
        rollover counter every now often (every 15 minutes). That is because of
        a reasonable expectation that request ID is used right away and call
        timeout won't be in minutes.
        """
        tmono = time.monotonic()
        if cls._last_request_id_rollover + (15 * 60) < tmono:
            cls._last_request_id = 0
            cls._last_request_id_rollover = tmono
        cls._last_request_id += 1
        return cls._last_request_id

    def __init__(self, rpc_val: SHVIMap | None = None) -> None:
        if rpc_val is None:
            rpc_val = SHVIMap()
        self.value: SHVIMap = rpc_val

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcMessage) and shvmeta_eq(self.value, other.value)

    def __repr__(self) -> str:
        return f"<RpcMessage {self.value.meta!r}: {self.value!r}>"

    class Tag(enum.IntEnum):
        """Tags in Meta for RPC message."""

        META_TYPE_ID = 1
        META_TYPE_NAMESPACE_ID = 2
        REQUEST_ID = 8
        SHV_PATH = 9
        METHOD = 10
        SIGNAL = 10
        CALLER_IDS = 11
        REV_CALLER_IDS = 13
        ACCESS = 14
        USER_ID = 16
        ACCESS_LEVEL = 17
        SOURCE = 19
        REPEAT = 20

    class Key(enum.IntEnum):
        """Keys in the toplevel IMap of the RPC message."""

        PARAM = 1
        RESULT = 2
        ERROR = 3
        DELAY = 4
        ABORT = 5

    class Type(enum.Enum):
        """The message type definition.

        This is defined to allow message differenciate in ``match``. It is more
        specific than SHV standard to allow easier implementation of different
        messages handling.
        """

        REQUEST = enum.auto()
        REQUEST_ABORT = enum.auto()
        RESPONSE = enum.auto()
        RESPONSE_DELAY = enum.auto()
        RESPONSE_ERROR = enum.auto()
        SIGNAL = enum.auto()

    def is_valid(self) -> bool:
        """Check if message is valid RPC message."""
        return (
            isinstance(self.value, SHVIMap)  # Must be IMap
            and len(self.value) <= 1  # Only at most one Key is allowed
            and self.type is not None
            and self.value.meta.get(self.Tag.META_TYPE_ID, 1) == 1
            and self.value.meta.get(self.Tag.META_TYPE_NAMESPACE_ID, 0) == 0
            and isinstance(self._request_id, int | None)
            and isinstance(self._path, str)
            and isinstance(self._signal_name, str)  # Also covers method
            and (
                isinstance(self._caller_ids, int | None)
                or (
                    is_shvlist(self._caller_ids)
                    and all(isinstance(v, int) for v in self._caller_ids)
                )
            )
            and isinstance(self._access, str)
            and isinstance(self._user_id, str | None)
            and isinstance(self._access_level, int | None)
            and isinstance(self._source, str)
            and isinstance(self._repeat, bool)
            # TODO check value content
        )

    @property
    def type(self) -> Type | None:
        """The message type or ``None`` if unknown."""
        if self.Tag.REQUEST_ID in self.value.meta:
            if self.Tag.METHOD in self.value.meta:
                if self.Key.ABORT in self.value:
                    return self.Type.REQUEST_ABORT
                if not self.value or self.Key.PARAM in self.value:
                    return self.Type.REQUEST
            elif self.Key.ERROR in self.value:
                return self.Type.RESPONSE_ERROR
            elif self.Key.DELAY in self.value:
                return self.Type.RESPONSE_DELAY
            elif not self.value or self.Key.RESULT in self.value:
                return self.Type.RESPONSE
        elif not self.value or self.Key.PARAM in self.value:
            return self.Type.SIGNAL
        return None

    def make_response(self, result: SHVType | RpcError = None) -> RpcMessage:
        """Create new message that is response to this one.

        :param result: The result value to be set in the response or
          :py:class:`RpcError` to be reported as error result.
        :return: The new message that is response to this one.
        """
        if self.type not in {self.Type.REQUEST, self.Type.REQUEST_ABORT}:
            raise ValueError("Response can be created from request only.")
        resp = RpcMessage()
        resp.request_id = self.request_id
        resp.caller_ids = self.caller_ids
        if isinstance(result, RpcError):
            resp.error = result
        else:
            resp.result = result
        return resp

    def make_response_delay(self, progress: float = 0.0) -> RpcMessage:
        """Create new message that is response delay for this one.

        :param progress: The progress to be reported.
        :return: The new message that is response delay to this one.
        """
        if self.type not in {self.Type.REQUEST, self.Type.REQUEST_ABORT}:
            raise ValueError("Response delay can be created from request only.")
        resp = RpcMessage()
        resp.request_id = self.request_id
        resp.caller_ids = self.caller_ids
        resp.delay = progress
        return resp

    def make_abort(self, abort: bool) -> RpcMessage:
        """Create abort message for the request."""
        if self.type is not self.Type.REQUEST:
            raise ValueError("Abort request can be created from request only.")
        res = RpcMessage()
        res.request_id = self.request_id
        res.caller_ids = self.caller_ids
        res.method = self.method
        res.path = self.path
        res.abort = abort
        return res

    @property
    def _request_id(self) -> SHVType:
        return self.value.meta.get(self.Tag.REQUEST_ID)

    @property
    def request_id(self) -> int:
        """Request identifier of this message."""
        res = self._request_id
        if not isinstance(res, int):
            raise ValueError(f"Invalid RequestId type: {type(res)}")
        return res

    @request_id.setter
    def request_id(self, rqid: int | None) -> None:
        """Set given request identifier to this message."""
        if rqid is None:
            self.value.meta.pop(self.Tag.REQUEST_ID, None)
        else:
            self.value.meta[self.Tag.REQUEST_ID] = rqid

    def new_request_id(self) -> int:
        """Set new request ID.

        :return: The new request ID.
        """
        self.request_id = self.next_request_id()
        return self.request_id

    @property
    def _path(self) -> SHVType:
        return self.value.meta.get(self.Tag.SHV_PATH, "")

    @property
    def path(self) -> str:
        """SHV path specified for this message or empty string."""
        res = self._path
        if not isinstance(res, str):
            raise ValueError(f"Invalid ShvPath type: {type(res)}")
        return res

    @path.setter
    def path(self, path: str) -> None:
        """Set given path as SHV path for this message."""
        if path:
            self.value.meta[self.Tag.SHV_PATH] = path
        else:
            self.value.meta.pop(self.Tag.SHV_PATH, None)

    @property
    def shvpath(self) -> SHVPath:
        """SHV path specified for this message as :class:`SHVPath`."""
        return SHVPath(self.path)

    @shvpath.setter
    def shvpath(self, path: SHVPath) -> None:
        """Set given :class:`SHVPath` as SHV path for this message."""
        self.path = str(path)

    @property
    def method(self) -> str:
        """SHV method name for this message."""
        res = self.value.meta.get(self.Tag.METHOD)
        if not isinstance(res, str):
            raise ValueError(f"Invalid Method type: {type(res)}")
        return res

    @method.setter
    def method(self, method: str) -> None:
        """Set SHV method name for this message."""
        if method:
            self.value.meta[self.Tag.METHOD] = method
        else:
            self.value.meta.pop(self.Tag.METHOD, None)

    @property
    def _signal_name(self) -> SHVType:
        return self.value.meta.get(self.Tag.METHOD, "chng")

    @property
    def signal_name(self) -> str:
        """SHV signal name for this message."""
        res = self._signal_name
        if not isinstance(res, str):
            raise ValueError(f"Invalid Signal type: {type(res)}")
        return res

    @signal_name.setter
    def signal_name(self, signal: str) -> None:
        """Set SHV signal name for this message."""
        # Note: we always set it because old implementations were dropping
        # messages without method name.
        self.value.meta[self.Tag.SIGNAL] = signal

    @property
    def _source(self) -> SHVType:
        return self.value.meta.get(self.Tag.SOURCE, "get")

    @property
    def source(self) -> str:
        """SHV signal source method name for this message."""
        res = self._source
        if not isinstance(res, str):
            raise ValueError(f"Invalid Source type: {type(res)}")
        return res

    @source.setter
    def source(self, source: str) -> None:
        """Set SHV signal source method name for this message."""
        if source and source != "get":
            self.value.meta[self.Tag.SOURCE] = source
        else:
            self.value.meta.pop(self.Tag.SOURCE, None)

    @property
    def _caller_ids(self) -> SHVType:
        return self.value.meta.get(self.Tag.CALLER_IDS, None)

    @property
    def caller_ids(self) -> collections.abc.Sequence[int]:
        """Caller identifiers associated with this message."""
        res = self._caller_ids
        if res is None:
            return []
        if isinstance(res, int):
            return [res]
        if not is_shvlist(res) or any(not isinstance(v, int) for v in res):
            raise ValueError(f"Invalid CallerIds type: {type(res)}")
        # Mypy doesn't understand the any check and thus we have to type cast
        return typing.cast(collections.abc.Sequence[int], res)

    @caller_ids.setter
    def caller_ids(self, cids: collections.abc.Sequence[int]) -> None:
        """Set caller identifiers associated with this message."""
        if not cids:
            self.value.meta.pop(self.Tag.CALLER_IDS, None)
        elif len(cids) == 1:
            self.value.meta[self.Tag.CALLER_IDS] = cids[0]
        else:
            self.value.meta[self.Tag.CALLER_IDS] = cids

    @property
    def _access(self) -> SHVType:
        return self.value.meta.get(self.Tag.ACCESS, "")

    @property
    def access(self) -> collections.abc.Sequence[str]:
        """Granted access sequence."""
        res = self._access
        if not isinstance(res, str):
            raise ValueError(f"Invalid access type: {type(res)}")
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
    def _access_level(self) -> SHVType:
        return self.value.get(self.Tag.ACCESS_LEVEL)

    @property
    def rpc_access(self) -> RpcAccess | None:
        """Access level as :class:`shv.RpcAccess`."""
        if (level := self._access_level) is not None:
            if not isinstance(level, int):
                raise ValueError(f"Invalid AccessLevel type: {type(level)}")
            return RpcAccess(level)
        m = RpcAccess.strmap()
        for access in self.access:
            if access in m:
                return m[access]
        return None

    @rpc_access.setter
    def rpc_access(self, access: RpcAccess | None) -> None:
        """Set access level with :class:`shv.RpcAccess`."""
        if access is not None:
            self.value.meta[self.Tag.ACCESS] = RpcAccess.tostr(access)
            self.value.meta[self.Tag.ACCESS_LEVEL] = access.value
        else:
            self.value.meta.pop(self.Tag.ACCESS, None)

    @property
    def _user_id(self) -> SHVType:
        res = self.value.meta.get(self.Tag.USER_ID, None)
        if isinstance(res, dict):  # Note: backward compatibility
            res = f"{res.get('brokerId')}:{res.get('shvUser')}"
        return res

    @property
    def user_id(self) -> str | None:
        """User's ID carried by message."""
        res = self._user_id
        if not isinstance(res, str | None):
            raise ValueError(f"Invalid UserId type: {type(res)}")
        return res

    @user_id.setter
    def user_id(self, value: str | None) -> None:
        """Set User's ID."""
        if value is not None:
            self.value.meta[self.Tag.USER_ID] = value
        else:
            self.value.meta.pop(self.Tag.USER_ID, None)

    @property
    def _repeat(self) -> SHVType:
        return self.value.meta.get(self.Tag.REPEAT, False)

    @property
    def repeat(self) -> bool:
        """Signal is possibly a repeat of some previous signal."""
        res = self._repeat
        if not isinstance(res, bool):
            raise ValueError(f"Invalid Repeat type: {type(res)}")
        return res

    @repeat.setter
    def repeat(self, value: bool | None) -> None:
        """Set repeat."""
        if value is not None:
            self.value.meta[self.Tag.REPEAT] = value
        else:
            self.value.meta.pop(self.Tag.REPEAT, None)

    @property
    def param(self) -> SHVType:
        """SHV parameters for the method call.

        Usable only for :py:data:`Type.REQUEST` and :py:data:`Type.SIGNAL`.
        """
        return self.value.get(self.Key.PARAM, None)

    @param.setter
    def param(self, param: SHVType) -> None:
        """Set SHV parameters for this method call."""
        if param is None:
            self.value.pop(self.Key.PARAM, None)
        else:
            self.value[self.Key.PARAM] = param

    @property
    def abort(self) -> bool:
        """The delay progress for the :py:data:`Type.REQUEST_ABORT`."""
        res = self.value.get(self.Key.ABORT)
        if not isinstance(res, bool):
            raise ValueError(f"Invalid Abort: {res!r}")
        return res

    @abort.setter
    def abort(self, abort: bool | None) -> None:
        """Set SHV Request Delay progress."""
        if abort is None:
            self.value.pop(self.Key.ABORT, None)
        else:
            self.value[self.Key.ABORT] = abort

    @property
    def result(self) -> SHVType:
        """SHV method call result.

        Usable only for :py:data:`Type.RESPONSE`.
        """
        return self.value.get(self.Key.RESULT, None)

    @result.setter
    def result(self, result: SHVType) -> None:
        """Set SHV method call result."""
        if result is None:
            self.value.pop(self.Key.RESULT, None)
        else:
            self.value[self.Key.RESULT] = result

    @property
    def error(self) -> RpcError:
        """SHV method call error.

        Usable only for :py:data:`Type.ERROR`.
        """
        return RpcError.from_shv(self.value.get(self.Key.ERROR))

    @error.setter
    def error(self, error: RpcError | None) -> None:
        """Set SHV method call error."""
        if error is None or error.error_code == RpcErrorCode.NO_ERROR:
            self.value.pop(self.Key.ERROR, None)
        else:
            self.value[self.Key.ERROR] = error.to_shv()

    @property
    def delay(self) -> float:
        """The delay progress for the :py:data:`Type.RESPONSE_DELAY`."""
        res = self.value.get(self.Key.DELAY)
        if not isinstance(res, float):
            raise ValueError(f"Invalid Delay: {res!r}")
        return res

    @delay.setter
    def delay(self, progress: float | None) -> None:
        """Set SHV Request Delay progress."""
        if progress is None:
            self.value.pop(self.Key.DELAY, None)
        else:
            self.value[self.Key.DELAY] = progress

    def to_string(self) -> str:
        """Convert message to CPON and return it as string."""
        return self.to_cpon().decode("utf-8")

    def to_cpon(self) -> bytes:
        """Convert message to Cpon."""
        return CponWriter.pack(self.value)

    def to_chainpack(self) -> bytes:
        """Convert message to Chainpack."""
        return ChainPackWriter.pack(self.value)

    @classmethod
    def request(
        cls,
        path: str | SHVPath,
        method: str,
        param: SHVType = None,
        rid: int | None = None,
        cids: collections.abc.Sequence[int] = tuple(),
        user_id: str | None = None,
    ) -> RpcMessage:
        """Create request message.

        :param path: SHV path for signal.
        :param method: method name for signal.
        :param param: Parameters passed to the method.
        :param rid: Request identifier for this message. It is automatically
          assigned if ``None`` is passed.
        :param cids: The caller IDs. This can be used with methods using a
          unique CallerIds sequence to establish session.
        :param user_id: User's ID to be caried with request message.
        """
        res = cls()
        res.request_id = rid or cls.next_request_id()
        res.caller_ids = cids
        res.method = method
        res.path = str(path)
        res.param = param
        res.user_id = user_id
        return res

    @classmethod
    def signal(
        cls,
        path: str | SHVPath,
        name: str = "chng",
        source: str = "get",
        value: SHVType = None,
        access: RpcAccess = RpcAccess.READ,
        user_id: str | None = None,
    ) -> RpcMessage:
        """Create signal message.

        :param path: SHV path for signal.
        :param name: Name of the signal.
        :param source: Name of the method this signal is associated with.
        :param value: Value to be sent in the message.
        :param access: Minimal access level needed to get this signal.
        :param user_id: User ID associated with this signal.
        """
        res = cls()
        res.signal_name = name
        res.source = source
        res.path = str(path)
        res.param = value
        res.rpc_access = access
        res.user_id = user_id
        return res

    @classmethod
    def lsmod(
        cls, path: str | SHVPath, nodes: collections.abc.Mapping[str, bool]
    ) -> RpcMessage:
        """Create ``lsmod`` signal message.

        This provides creation of "lsmod" signal message that must be used when
        you are changing the nodes tree to signal clients about that. The
        argument specifies top level nodes added or removed (based on the
        mapping value).

        :param path: SHV path to the valid node which children were added or
          removed.
        :param nodes: Map where key is node name of the node that is top level
          node, that was either added (for value ``True``) or removed (for value
          ``False``).
        """
        return cls.signal(path, "lsmod", "ls", nodes, RpcAccess.BROWSE)
