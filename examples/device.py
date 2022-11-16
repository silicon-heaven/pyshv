import asyncio
import logging

from libshv.chainpack.rpcclient import RpcClient
from libshv.chainpack.rpcmessage import RpcMessage

logging.basicConfig(
    level=logging.DEBUG, format="%(levelname)s[%(module)s:%(lineno)d] %(message)s"
)

FLAG_SIGNAL = 1
FLAG_GETTER = 2
FLAG_SETTER = 4


async def client_loop():
    client = RpcClient()
    print("connecting to broker")
    await client.connect(
        host="localhost",
        password="test",
        user="test",
        login_type=RpcClient.LoginType.Plain,
        mount_point="test/device",
    )

    tracks = {}
    for i in range(1, 9):
        tracks[str(i)] = [n for n in range(i)]

    while True:
        msg = await client.read_rpc_message()
        if msg.is_request():
            print("RPC request received:", msg.to_string())
            path_str = msg.shv_path().to_str()
            if len(path_str) == 0:
                path = []
            else:
                path = path_str.split("/")
            method = msg.method().to_str()
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
                        resp.set_result([t for t in tracks.keys()])
                elif len(path) == 1:
                    track = path[0]
                    if method == "dir":
                        resp.set_result(
                            [
                                {"accessGrant": "bws", "flags": 0, "name": "dir"},
                                {
                                    "accessGrant": "rd",
                                    "flags": FLAG_GETTER,
                                    "name": "get",
                                },
                                {
                                    "accessGrant": "wr",
                                    "flags": FLAG_SETTER,
                                    "name": "set",
                                },
                            ]
                        )
                    elif method == "get":
                        resp.set_result(tracks[track])
                    elif method == "set":
                        old_val = tracks[track]
                        new_val = msg.params()
                        tracks[track] = new_val
                        resp.set_result(True)
                        if old_val != new_val:
                            sig = RpcMessage()
                            sig.set_method("chng")
                            sig.set_shv_path("track/" + track)
                            sig.set_params(new_val)
                            await client.send_rpc_message(sig)
            if resp.result() is None:
                resp.set_error("Invalid request: " + msg.to_string())
            await client.send_rpc_message(resp)
        elif msg.is_response():
            print("RPC response received:", msg.to_string())
        elif msg.is_signal():
            print("RPC signal received:", msg.to_string())


if __name__ == "__main__":
    loop = asyncio.run(client_loop())
