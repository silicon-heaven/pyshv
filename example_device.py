#!/usr/bin/env python3
import argparse
import asyncio
import logging
import typing

from shv import (
    RpcClient,
    RpcInvalidParamsError,
    RpcMessage,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    RpcMethodSignature,
    RpcUrl,
    SHVType,
    SimpleClient,
)

log_levels = (
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
)


class ExampleDevice(SimpleClient):
    """Simple device demostrating the way to implement request handling."""

    APP_NAME = "pyshv-example_device"

    def __init__(self, client: RpcClient, client_id: int | None):
        super().__init__(client, client_id)
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}

    def _ls(self, path: str) -> typing.Iterator[str]:
        yield from super()._ls(path)
        pth = path.split("/") if path else []
        if len(pth) == 0:
            yield "track"
        elif pth[0] == "track":
            if len(pth) == 1:
                yield from self.tracks.keys()

    def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        pth = path.split("/") if path else []
        if len(pth) == 2 and pth[0] == "track" and pth[1] in self.tracks:
            yield RpcMethodDesc(
                "get",
                RpcMethodSignature.RET_VOID,
                RpcMethodFlags.GETTER,
                RpcMethodAccess.READ,
                "Get current track",
            )
            yield RpcMethodDesc(
                "set",
                RpcMethodSignature.VOID_PARAM,
                RpcMethodFlags.SETTER,
                RpcMethodAccess.WRITE,
                "Set track",
            )

    async def _method_call(
        self, path: str, method: str, access: RpcMethodAccess, params: SHVType
    ) -> SHVType:
        pth = path.split("/") if path else []
        if len(pth) == 2 and pth[1] in self.tracks:
            if method == "get" and access >= RpcMethodAccess.READ:
                return self.tracks[pth[1]]
            if method == "set" and access >= RpcMethodAccess.WRITE:
                if not isinstance(params, list) or not all(
                    isinstance(v, int) for v in params
                ):
                    raise RpcInvalidParamsError("Only list of ints is accepted.")
                old_track = self.tracks[pth[1]]
                self.tracks[pth[1]] = params
                if old_track != params:
                    await self.client.send(RpcMessage.chng("track/" + pth[1], params))
                return True
        return await super()._method_call(path, method, access, params)


async def example_device(url: RpcUrl):
    client = await ExampleDevice.connect(url)
    if client is not None:
        await client.task


def parse_args():
    """Parse passed arguments and return result."""
    parser = argparse.ArgumentParser(
        "example_device", description="Silicon Heaven example device"
    )
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="Increase verbosity level of logging",
    )
    parser.add_argument(
        "-q",
        action="count",
        default=0,
        help="Decrease verbosity level of logging",
    )
    parser.add_argument(
        "URL",
        nargs="?",
        default="tcp://test@localhost?password=test&devmount=test/device",
        help="SHV RPC URL specifying connection to the broker.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(
        level=log_levels[sorted([1 - args.v + args.q, 0, len(log_levels) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )
    asyncio.run(example_device(RpcUrl.parse(args.URL)))
