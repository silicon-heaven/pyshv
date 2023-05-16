#!/usr/bin/env python3
import asyncio
import collections.abc
import enum
import logging

from shv import RpcClient, RpcInvalidParamsError, RpcMessage

logging.basicConfig(
    level=logging.DEBUG, format="%(levelname)s[%(module)s:%(lineno)d] %(message)s"
)


class MethodFlags(enum.IntFlag):
    SIGNAL = 1
    GETTER = 2
    SETTER = 4


tracks = {str(i): list(range(i)) for i in range(1, 9)}


async def handle_message(client: RpcClient, msg: RpcMessage) -> None:
    if msg.is_request():
        print("RPC request received:", msg.to_string())
        path_str = msg.shv_path() or ""
        if len(path_str) == 0:
            path = []
        else:
            path = path_str.split("/")
        method = msg.method()
        resp = msg.make_response()
        if len(path) == 0:
            if method == "dir":
                resp.set_result(
                    [
                        {"accessGrant": "bws", "flags": 0, "name": "dir"},
                        {"accessGrant": "bws", "flags": 0, "name": "ls"},
                    ]
                )
            elif method == "ls":
                resp.set_result(["track"])
        elif path[0] == "track":
            path = path[1:]
            if len(path) == 0:
                if method == "dir":
                    resp.set_result(
                        [
                            {"accessGrant": "bws", "flags": 0, "name": "dir"},
                            {"accessGrant": "bws", "flags": 0, "name": "ls"},
                        ]
                    )
                elif method == "ls":
                    resp.set_result(list(tracks.keys()))
            elif len(path) == 1:
                track = path[0]
                if method == "dir":
                    resp.set_result(
                        [
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
                    )
                elif method == "get":
                    resp.set_result(tracks[track])
                elif method == "set":
                    old_val = tracks[track]
                    new_val = msg.params()
                    if isinstance(new_val, list) and all(
                        isinstance(v, int) for v in new_val
                    ):
                        tracks[track] = new_val
                        resp.set_result(True)
                        if old_val != new_val:
                            sig = RpcMessage()
                            sig.set_method("chng")
                            sig.set_shv_path("track/" + track)
                            sig.set_params(new_val)
                            await client.send_rpc_message(sig)
                    else:
                        resp.set_rpc_error(
                            RpcInvalidParamsError("Only list of ints is accepted.")
                        )
        if resp.result() is None:
            resp.set_error("Invalid request: " + msg.to_string())
        await client.send_rpc_message(resp)
    elif msg.is_response():
        print("RPC response received:", msg.to_string())
    elif msg.is_signal():
        print("RPC signal received:", msg.to_string())


async def example_device(port=3755):
    client = await RpcClient.connect(
        host="localhost",
        port=port,
    )
    await client.login_device(
        mount_point="test/device",
        user="test",
        password="test",
        login_type=RpcClient.LoginType.PLAIN,
    )
    client.callback = handle_message
    await client.read_loop()


if __name__ == "__main__":
    loop = asyncio.run(example_device())
