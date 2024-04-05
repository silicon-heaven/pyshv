"""RPC client that represents device in a physical sense."""

import collections.abc

from .rpcmethod import RpcMethodAccess, RpcMethodDesc
from .simpleclient import SimpleClient
from .value import SHVType


class SimpleDevice(SimpleClient):
    """SHV client that represents a physical device."""

    APP_NAME: str = "pyshv-device"

    DEVICE_NAME: str = "unknown"
    """String identifier for the physical device."""

    DEVICE_VERSION: str = "unknown"
    """The physical device design version."""

    DEVICE_SERIAL_NUMBER: str | None = None
    """Serial number of the physical device."""

    async def _method_call(
        self,
        path: str,
        method: str,
        param: SHVType,
        access: RpcMethodAccess,
        user_id: str | None,
    ) -> SHVType:
        match path, method:
            case ".device", "name":
                return self.DEVICE_NAME
            case ".device", "version":
                return self.DEVICE_VERSION
            case ".device", "serialNumber" if access >= RpcMethodAccess.READ:
                return self.DEVICE_SERIAL_NUMBER
        return await super()._method_call(path, method, param, access, user_id)

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

    async def _lsmod(
        self, path: str, nodes: collections.abc.Mapping[str, bool]
    ) -> None:
        """Report change in the ls method.

        This provides implementation for "lsmod" signal that must be used when
        you are changing the nodes tree to signal clients about that. The
        argument specifies top level nodes added or removed (based on the
        mapping value).

        :param path: SHV path to the valid node which children were added or
          removed.
        :param nodes: Map where key is node name of the node that is top level
          node, that was either added (for value ``True``) or removed (for value
          ``False``).
        """
        await self._signal(path, "lsmod", "ls", nodes, RpcMethodAccess.BROWSE)
