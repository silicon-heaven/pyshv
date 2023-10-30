"""RPC client that represents device in a physical sense."""
import typing

from .rpcmethod import RpcMethodAccess, RpcMethodDesc
from .simpleclient import SimpleClient
from .value import SHVType


class SimpleDevice(SimpleClient):
    """SHV client that represents a physical device."""

    DEVICE_NAME: str = "unknown"
    """String identifier for the physical device."""

    DEVICE_VERSION: str = "unknown"
    """The physical device design version."""

    DEVICE_SERIAL_NUMBER: str | None = None
    """Serial number of the physical device."""

    async def _method_call(
        self, path: str, method: str, access: RpcMethodAccess, param: SHVType
    ) -> SHVType:
        if path == ".app/device":
            match method:
                case "name":
                    return self.DEVICE_NAME
                case "version":
                    return self.DEVICE_VERSION
                case "serialNumber":
                    return self.DEVICE_SERIAL_NUMBER
        return await super()._method_call(path, method, access, param)

    def _ls(self, path: str) -> typing.Iterator[str]:
        yield from super()._ls(path)
        # Parent already yield .app
        if path == ".app":
            yield "device"

    def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        if path == ".app/device":
            yield RpcMethodDesc.getter(
                "name", "Null", "String", access=RpcMethodAccess.BROWSE
            )
            yield RpcMethodDesc.getter(
                "version", "Null", "String", access=RpcMethodAccess.BROWSE
            )
            yield RpcMethodDesc.getter(
                "serialNumber", "Null", "OptionalString", access=RpcMethodAccess.BROWSE
            )
