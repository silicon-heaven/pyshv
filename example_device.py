#!/usr/bin/env python3
"""Example demonstratrating how device application can be written with pySHV."""

import argparse
import asyncio
import collections.abc
import logging
import typing

from shv import (
    RpcInvalidParamError,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    RpcUrl,
    SHVBase,
    SHVClient,
    SHVMethods,
    SHVType,
)


class ExampleDevice(SHVClient, SHVMethods):
    """Simple device demostrating the way to implement request handling."""

    APP_NAME = "pyshv-example_device"

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:  # noqa ANN401
        super().__init__(*args, **kwargs)
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
        self.last_reset_user: None | str = None

    @SHVMethods.property("numberOfTracks", signal=True)
    def number_of_tracks(self, oldness: int | None) -> SHVType:
        """SHV property getter numberOfTrack."""
        return len(self.tracks)

    @number_of_tracks.setter  # type: ignore[no-redef]
    async def number_of_tracks(self, param: SHVType, user_id: str | None) -> None:
        """SHV property getter numberOfTrack."""
        if not isinstance(param, int) or param < 1:
            raise RpcInvalidParamError("Int greater than 0 expected")
        oldlen = len(self.tracks)
        if oldlen != param:
            self.tracks = {
                str(i): self.tracks[str(i)] if oldlen > i else list(range(i))
                for i in range(1, param + 1)
            }
            await self.number_of_tracks(param, user_id=user_id)
            await self._lsmod(
                "track",
                {
                    str(i): oldlen < param
                    for i in range(min(oldlen, param), max(oldlen, param))
                },
            )

    @SHVMethods.method(
        "track",
        RpcMethodDesc(
            "reset",
            RpcMethodFlags.USER_ID_REQUIRED,
            access=RpcMethodAccess.COMMAND,
            extra={"description": "Reset all tracks to their initial state"},
        ),
    )
    async def track_reset(self, request: SHVBase.Request) -> SHVType:
        """SHV method track:reset."""
        self.last_reset_user = request.user_id
        old = self.tracks
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
        for k in old:
            if old[k] != self.tracks[k]:
                await self._signal(f"track/{k}", value=self.tracks[k])
        return None

    @SHVMethods.method("track", RpcMethodDesc.getter("lastResetUser", result="s|n"))
    async def track_last_reset_user(self, request: SHVBase.Request) -> SHVType:
        """SHV method track:lastResetUser."""
        return self.last_reset_user

    def _ls(self, path: str) -> collections.abc.Iterator[str]:
        yield from super()._ls(path)
        yield from self._ls_node_for_path(
            path, (f"track/{i}" for i in self.tracks.keys())
        )

    def _dir(self, path: str) -> collections.abc.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        match path.split("/"):
            case ["track", track] if track in self.tracks:
                yield RpcMethodDesc.getter(
                    result="List[Int]", description="List of tracks", signal=True
                )
                yield RpcMethodDesc.setter(param="List[Int]", description="Set track")

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        match request.path.split("/"), request.method:
            case [["track", track], _] if track in self.tracks:
                if request.method == "get" and request.access >= RpcMethodAccess.READ:
                    return self.tracks[track]
                if request.method == "set" and request.access >= RpcMethodAccess.WRITE:
                    if not isinstance(request.param, list) or not all(
                        isinstance(v, int) for v in request.param
                    ):
                        raise RpcInvalidParamError("Only list of ints is accepted.")
                    old_track = self.tracks[track]
                    self.tracks[track] = request.param
                    if old_track != request.param:
                        await self._signal(f"track/{track}", value=request.param)
                    return None
        return await super()._method_call(request)

    @classmethod
    async def run(cls, url: RpcUrl) -> None:
        """Coroutine that starts example device and waits for its termination."""
        client = await cls.connect(url)
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
        level=logging.WARNING + 10 * (pargs.q - pargs.v),
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )
    asyncio.run(ExampleDevice.run(RpcUrl.parse(pargs.URL)))
