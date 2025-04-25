"""RPC client that represents device in a physical sense."""

from __future__ import annotations

import collections.abc
import itertools
import time
import typing

from .rpcaccess import RpcAccess
from .rpcalert import RpcAlert
from .rpcdir import RpcDir
from .rpcerrors import RpcNotImplementedError
from .rpcmessage import RpcMessage
from .shvbase import SHVBase
from .shvclient import SHVClient
from .value import SHVType


class SHVDevice(SHVClient):
    """SHV client that represents a physical device."""

    APP_NAME: str = "pyshv-device"

    DEVICE_NAME: str = "unknown"
    """String identifier for the physical device."""

    DEVICE_VERSION: str = "unknown"
    """The physical device design version."""

    DEVICE_SERIAL_NUMBER: str | None = None
    """Serial number of the physical device."""

    DEVICE_ALERTS: bool = True
    """Control if alerts will be available in the SHV Device."""

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:  # noqa ANNN401
        self._alerts: list[RpcAlert] = []
        super().__init__(*args, **kwargs)  # notype

    @property
    def alerts(self) -> collections.abc.Iterator[RpcAlert]:
        """Iterate over all current alerts."""
        return iter(self._alerts)

    async def change_alerts(
        self,
        add: RpcAlert | collections.abc.Collection[RpcAlert] = tuple(),
        rem: RpcAlert | collections.abc.Collection[RpcAlert] = tuple(),
    ) -> None:
        """Add (or update) given alert.

        :param alert: The alert to be added to the list. Any previous alert with
          same level is replaced.
        """
        if isinstance(add, RpcAlert):
            add = (add,)
        if isinstance(rem, RpcAlert):
            rem = (rem,)
        if not add and not rem:
            return
        self._alerts = list(
            itertools.chain(
                (old for old in self._alerts if old not in add and old not in rem),
                iter(add),
            )
        )
        self._alerts.sort(key=lambda a: a.id)
        await self._send(
            RpcMessage.signal(
                ".device/alerts", value=[alert.value for alert in self._alerts]
            )
        )

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        match request.path, request.method:
            case ".device", "name":
                return self.DEVICE_NAME
            case ".device", "version":
                return self.DEVICE_VERSION
            case ".device", "serialNumber" if request.access >= RpcAccess.READ:
                return self.DEVICE_SERIAL_NUMBER
            case ".device", "uptime":
                return int(time.monotonic())
            case ".device", "reset" if request.access >= RpcAccess.COMMAND:
                self._device_reset()
                return None  # pragma: no cover
            case ".device/alerts", "get" if (
                self.DEVICE_ALERTS and request.access >= RpcAccess.READ
            ):
                return [alert.value for alert in self._alerts]
        return await super()._method_call(request)

    def _ls(self, path: str) -> collections.abc.Iterator[str]:
        yield from super()._ls(path)
        match path:
            case "":
                yield ".device"
            case ".device" if self.DEVICE_ALERTS:
                yield "alerts"

    def _dir(self, path: str) -> collections.abc.Iterator[RpcDir]:
        yield from super()._dir(path)
        match path:
            case ".device":
                yield RpcDir.getter("name", "n", "s", access=RpcAccess.BROWSE)
                yield RpcDir.getter("version", "n", "s", access=RpcAccess.BROWSE)
                yield RpcDir.getter("serialNumber", "n", "s|n", access=RpcAccess.BROWSE)
                yield RpcDir.getter("uptime", "n", "u|n", access=RpcAccess.BROWSE)
                yield RpcDir("reset", access=RpcAccess.COMMAND)
            case ".device/alerts" if self.DEVICE_ALERTS:
                yield RpcDir.getter(result="[!alert]", signal=True)

    def _device_reset(self) -> None:  # noqa: PLR6301
        """Trigger called to perform the device reset."""
        raise RpcNotImplementedError
