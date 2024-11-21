"""RPC client that represents device in a physical sense."""

import collections.abc

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

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        match request.path, request.method:
            case ".device", "name":
                return self.DEVICE_NAME
            case ".device", "version":
                return self.DEVICE_VERSION
            case ".device", "serialNumber" if request.access >= RpcMethodAccess.READ:
                return self.DEVICE_SERIAL_NUMBER
        return await super()._method_call(request)

    def _ls(self, path: str) -> collections.abc.Iterator[str]:
        yield from super()._ls(path)
        if not path:
            yield ".device"

    def _dir(self, path: str) -> collections.abc.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        if path == ".device":
            yield RpcMethodDesc.getter(
                "name", "Null", "String", access=RpcMethodAccess.BROWSE
            )
            yield RpcMethodDesc.getter(
                "version", "Null", "String", access=RpcMethodAccess.BROWSE
            )
            yield RpcMethodDesc.getter(
                "serialNumber", "Null", "OptionalString", access=RpcMethodAccess.BROWSE
            )
