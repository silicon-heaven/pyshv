"""SHV RPC SimpleBase that collects and provides history."""

import collections.abc
import logging
import typing

from .. import (
    RpcClient,
    RpcMessage,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    SHVType,
    SimpleBase,
    shvargt,
)
from .files import RpcLogFiles
from .log import RpcLog, RpcLogClone
from .record import RpcHistoryRecord
from .records import RpcLogRecords

logger = logging.getLogger(__name__)


class RpcHistoryBase(SimpleBase):
    """SHV RPC Base that connects to server and mounts itself to .history.

    It records all received notifications to the database and provides access to
    this recorded history.

    This implements RPC History without client functionality. You can use this
    to combine it with some other classes based on :class:`SimpleBase`.
    """

    def __init__(
        self,
        client: RpcClient,
        logs: collections.abc.Sequence[RpcLog],
        *args: typing.Any,  # noqa ANN401
        **kwargs: typing.Any,  # noqa ANN401
    ) -> None:
        super().__init__(client, *args, **kwargs)
        self.logs = logs

    async def _message(self, msg: RpcMessage) -> None:
        await super()._message(msg)
        if msg.is_signal:
            rec = RpcHistoryRecord.new(msg)
            for log in self.logs:
                log.add(rec)

    def _ls(self, path: str) -> collections.abc.Iterator[str]:
        yield from super()._ls(path)
        for log in self.logs:
            shvpath = log.shvpath if isinstance(log, RpcLogClone) else ""
            if isinstance(log, RpcLogRecords):
                if path == shvpath:
                    yield ".records"
                elif path == f"{shvpath}/.records":
                    yield log.name
            elif isinstance(log, RpcLogFiles):
                if path == shvpath:
                    yield ".files"
                elif path == f"{shvpath}/.files":
                    yield log.name
                elif path == f"{shvpath}/.files/{log.name}":
                    pass  # TODO list files in the log
            if path and shvpath.startswith(path + ("/" if path else "")):
                yield shvpath[len(path) + 1 :].partition("/")[0]
            elif path == shvpath or path.startswith(path + "/"):
                yield from log.nodes(path[len(shvpath) + 1 :])

    def _dir(self, path: str) -> collections.abc.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        pth = path.split("/")
        if all(n not in {".records", ".files"} for n in pth):
            yield RpcMethodDesc(
                "getLog",
                RpcMethodFlags.LARGE_RESULT_HINT,
                "ilog",
                "olog",
                RpcMethodAccess.READ,
            )
            return
        for log in self.logs:
            shvpath = log.shvpath if isinstance(log, RpcLogClone) else ""
            if isinstance(log, RpcLogRecords):
                if path == f"{shvpath}/.records/{log.name}":
                    yield RpcMethodDesc(
                        "span",
                        RpcMethodFlags.GETTER,
                        "Null",
                        "oSpan",
                        RpcMethodAccess.SUPER_SERVICE,
                    )
                    yield RpcMethodDesc(
                        "fetch",
                        RpcMethodFlags(0),
                        "iFetch",
                        "oFetch",
                        RpcMethodAccess.SUPER_SERVICE,
                    )
                    if isinstance(log, RpcLogClone):
                        yield RpcMethodDesc.getter(
                            "info",
                            "Null",
                            "histat",
                            RpcMethodAccess.SUPER_SERVICE,
                        )
                        # TODO pull and push
            elif isinstance(log, RpcLogFiles):
                # if path == f"{shvpath}/.files/{log.name}{filename}":
                pass  # TODO list files in the log

    async def _method_call(
        self,
        path: str,
        method: str,
        param: SHVType,
        access: RpcMethodAccess,
        user_id: str | None,
    ) -> SHVType:
        for log in self.logs:
            shvpath = f"{log.shvpath}/" if isinstance(log, RpcLogClone) else ""
            if (
                isinstance(log, RpcLogRecords)
                and path == f"{shvpath}.records/{log.name}"
            ):
                if method == "span":
                    return log.span()
                if method == "fetch":
                    off = shvargt(param, 0, int)
                    cnt = shvargt(param, 1, int, 100)
                    return [r.to_shv() for r in log.records(off, off + cnt - 1)]
            elif isinstance(log, RpcLogFiles):
                pass  # TODO
        return await super()._method_call(path, method, param, access, user_id)
