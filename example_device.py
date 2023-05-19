#!/usr/bin/env python3
import asyncio
import enum
import logging

from shv import RpcClient, RpcInvalidParamsError, RpcMessage, SHVType, SimpleClient

logging.basicConfig(
    level=logging.DEBUG, format="%(levelname)s[%(module)s:%(lineno)d] %(message)s"
)


class MethodFlags(enum.IntFlag):
    SIGNAL = 1
    GETTER = 2
    SETTER = 4


class ExampleDevice(SimpleClient):
    """Simple device demostrating the way to implement request handling."""

    def __init__(self, client: RpcClient, client_id: int | None):
        super().__init__(client, client_id)
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}

    async def _method_call(
        self,
        path: str | None,
        method: str | None,
        params: SHVType,
    ) -> SHVType:
        pth = path.split("/") if path else []
        if len(pth) == 0:
            if method == "dir":
                return [
                    {"accessGrant": "bws", "flags": 0, "name": "dir"},
                    {"accessGrant": "bws", "flags": 0, "name": "ls"},
                ]
            if method == "ls":
                return ["track"]
        elif pth[0] == "track":
            pth = pth[1:]
            if len(pth) == 0:
                if method == "dir":
                    return [
                        {"accessGrant": "bws", "flags": 0, "name": "dir"},
                        {"accessGrant": "bws", "flags": 0, "name": "ls"},
                    ]
                if method == "ls":
                    return list(self.tracks.keys())
            elif len(pth) == 1:
                track = pth[0]
                if method == "dir":
                    return [
                        {"accessGrant": "bws", "flags": 0, "name": "dir"},
                        {
                            "accessGrant": "rd",
                            "flags": MethodFlags.GETTER,
                            "name": "get",
                        },
                        {
                            "accessGrant": "wr",
                            "flags": MethodFlags.SETTER,
                            "name": "set",
                        },
                    ]
                if method == "ls":
                    return []
                if method == "get":
                    return self.tracks[track]
                if method == "set":
                    if isinstance(params, list) and all(
                        isinstance(v, int) for v in params
                    ):
                        old_track = self.tracks[track]
                        self.tracks[track] = params
                        if old_track != params:
                            sig = RpcMessage()
                            sig.set_method("chng")
                            sig.set_shv_path("track/" + track)
                            sig.set_params(params)
                            await self.client.send_rpc_message(sig)
                        return True
                    raise RpcInvalidParamsError("Only list of ints is accepted.")
        return await super()._method_call(path, method, params)


async def example_device(port=3755):
    client = await ExampleDevice.connect(
        host="localhost",
        port=port,
        user="test",
        password="test",
        login_type=SimpleClient.LoginType.PLAIN,
        login_options={"device": {"mountPoint": "test/device"}},
    )
    await client.task


if __name__ == "__main__":
    asyncio.run(example_device())
