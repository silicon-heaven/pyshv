"""RPC client that represents device in a physical sense."""

import collections.abc
import itertools
import typing

from .rpcalert import RpcAlert
from .rpcmethod import RpcMethodAccess, RpcMethodDesc
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
    """Constrol if alerts will be available in the SHV Device."""

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
        await self._signal(
            ".device/alerts", value=[alert.value for alert in self._alerts]
        )

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        match request.path, request.method:
            case ".device", "name":
                return self.DEVICE_NAME
            case ".device", "version":
                return self.DEVICE_VERSION
            case ".device", "serialNumber" if request.access >= RpcMethodAccess.READ:
                return self.DEVICE_SERIAL_NUMBER
            case ".device/alerts", "get" if (
                self.DEVICE_ALERTS and request.access >= RpcMethodAccess.READ
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

    def _dir(self, path: str) -> collections.abc.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        match path:
            case ".device":
                yield RpcMethodDesc.getter(
                    "name", "Null", "String", access=RpcMethodAccess.BROWSE
                )
                yield RpcMethodDesc.getter(
                    "version", "Null", "String", access=RpcMethodAccess.BROWSE
                )
                yield RpcMethodDesc.getter(
                    "serialNumber",
                    "Null",
                    "OptionalString",
                    access=RpcMethodAccess.BROWSE,
                )
            case ".device/alerts" if self.DEVICE_ALERTS:
                yield RpcMethodDesc.getter(result="[i{...},...]", signal=True)