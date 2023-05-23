#!/usr/bin/env python3
import asyncio
import collections.abc
import logging

from shv import (
    DeviceClient,
    RpcClient,
    RpcInvalidParamsError,
    RpcMessage,
    RpcMethodFlags,
    RpcMethodSignature,
    SHVType,
)


class ExampleDevice(DeviceClient):
    """Simple device demostrating the way to implement request handling."""

    def __init__(self, client: RpcClient, client_id: int | None):
        super().__init__(client, client_id)
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}

    async def _ls(self, path: str) -> collections.abc.Sequence[tuple[str, bool]] | None:
        pth = path.split("/") if path else []
        if len(pth) == 0:
            return [("track", True)]
        if pth[0] == "track":
            if len(pth) == 1:
                return [(k, False) for k in self.tracks.keys()]
            if len(pth) == 2 and pth[1] in self.tracks:
                return []
        return await super()._ls(path)

    async def _dir(
        self, path: str
    ) -> collections.abc.Sequence[
        tuple[str, RpcMethodSignature, RpcMethodFlags, str, str]
    ] | None:
        pth = path.split("/") if path else []
        if len(pth) == 0:
            return [
                (
                    "appName",
                    RpcMethodSignature.RET_VOID,
                    RpcMethodFlags.GETTER,
                    "rd",
                    "",
                ),
                (
                    "appVersion",
                    RpcMethodSignature.RET_VOID,
                    RpcMethodFlags.GETTER,
                    "rd",
                    "",
                ),
                (
                    "echo",
                    RpcMethodSignature.RET_PARAM,
                    RpcMethodFlags(0),
                    "wr",
                    "",
                ),
            ]
        if pth[0] == "track":
            if len(pth) == 1:
                return []
            if len(pth) == 2 and pth[1] in self.tracks:
                return [
                    (
                        "get",
                        RpcMethodSignature.RET_VOID,
                        RpcMethodFlags.GETTER,
                        "rd",
                        "Get current track",
                    ),
                    (
                        "set",
                        RpcMethodSignature.VOID_PARAM,
                        RpcMethodFlags.SETTER,
                        "wr",
                        "Set track",
                    ),
                ]
        return await super()._dir(path)

    async def _method_call(self, path: str, method: str, params: SHVType) -> SHVType:
        pth = path.split("/") if path else []
        if len(pth) == 0:
            if method == "appName":
                return "pyshv-example_device"
            if method == "appVersion":
                return "unknown"
            if method == "echo":
                return params
        if len(pth) == 2 and pth[1] in self.tracks:
            if method == "get":
                return self.tracks[pth[1]]
            if method == "set":
                if not isinstance(params, list) or not all(
                    isinstance(v, int) for v in params
                ):
                    raise RpcInvalidParamsError("Only list of ints is accepted.")
                old_track = self.tracks[pth[1]]
                self.tracks[pth[1]] = params
                if old_track != params:
                    sig = RpcMessage()
                    sig.set_method("chng")
                    sig.set_shv_path("track/" + pth[1])
                    sig.set_params(params)
                    await self.client.send_rpc_message(sig)
                return True
        return await super()._method_call(path, method, params)


async def example_device(port=3755):
    client = await ExampleDevice.connect(
        host="localhost",
        port=port,
        user="test",
        password="test",
        login_type=DeviceClient.LoginType.PLAIN,
        mount_point="test/device",
    )
    await client.task


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG, format="%(levelname)s[%(module)s:%(lineno)d] %(message)s"
    )
    asyncio.run(example_device())
