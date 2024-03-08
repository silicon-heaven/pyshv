#!/usr/bin/env python3
import argparse
import asyncio
import logging
import typing

from shv import (
    RpcInvalidParamsError,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    RpcUrl,
    RpcUserIDRequiredError,
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

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
        self.last_reset_user: None | str = None

    def _ls(self, path: str) -> typing.Iterator[str]:
        yield from super()._ls(path)
        match path:
            case "":
                yield "track"
            case "track":
                yield from self.tracks.keys()

    def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        match path.split("/"):
            case ["track"]:
                yield RpcMethodDesc(
                    "reset",
                    RpcMethodFlags.USER_ID_REQUIRED,
                    access=RpcMethodAccess.COMMAND,
                    description="Reset all tracks to their initial state",
                )
                yield RpcMethodDesc.getter("lastResetUser", result="StringOrNull")
            case ["track", track] if track in self.tracks:
                yield RpcMethodDesc.getter(
                    result="List[Int]", description="List of tracks"
                )
                yield RpcMethodDesc.setter(param="List[Int]", description="Set track")

    async def _method_call(
        self,
        path: str,
        method: str,
        param: SHVType,
        access: RpcMethodAccess,
        user_id: str | None,
    ) -> SHVType:
        match path.split("/"), method:
            case ["track"], "reset" if access >= RpcMethodAccess.COMMAND:
                if user_id is None:
                    raise RpcUserIDRequiredError
                self.last_reset_user = user_id
                old = self.tracks
                self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
                for k in old:
                    if old[k] != self.tracks[k]:
                        await self.signal(f"track/{k}", value=self.tracks[k])
                return None
            case ["track"], "lastResetUser" if access >= RpcMethodAccess.READ:
                return self.last_reset_user
            case ["track", track], _ if track in self.tracks:
                if method == "get" and access >= RpcMethodAccess.READ:
                    return self.tracks[track]
                if method == "set" and access >= RpcMethodAccess.WRITE:
                    if not isinstance(param, list) or not all(
                        isinstance(v, int) for v in param
                    ):
                        raise RpcInvalidParamsError("Only list of ints is accepted.")
                    old_track = self.tracks[track]
                    self.tracks[track] = param
                    if old_track != param:
                        await self._signal(f"track/{track}", value=param)
                    return None
        return await super()._method_call(path, method, param, access, user_id)


async def example_device(url: RpcUrl) -> None:
    client = await ExampleDevice.connect(url)
    if client is not None:
        await client.task
        await client.disconnect()


def parse_args() -> argparse.Namespace:
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
    pargs = parse_args()
    logging.basicConfig(
        level=log_levels[sorted([1 - pargs.v + pargs.q, 0, len(log_levels) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )
    asyncio.run(example_device(RpcUrl.parse(pargs.URL)))
