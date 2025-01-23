"""Just for testing."""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Any

from shv import (
    RpcInvalidParamError,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    RpcUrl,
    RpcUserIDRequiredError,
    SHVBase,
    SHVClient,
    SHVType,
)


def shv_method(
    path: str,
    name: str,
    flags: RpcMethodFlags | None = None,
    access: RpcMethodAccess | None = None,
    signal: bool | str | None = None,
) -> Callable[[Callable], Callable]:
    """Return wrapper for annotating function ``fn``.

    NOTE: Instead of keyword arguments, we can put here ``RpcMethodDesc``
          -- only parameter missing from ``RpcMethodDesc`` is path.
          However, keyword arguments feel more convenient to use.

    ``fn`` is expected to be a method of the end-application class. The
    generator annotates that method with ``_svh`` information.

    To override the default metainformation, set ``shv_method`` parameters:

    :param path: SHV path (required.)
    :param name: SHV method name (required.)
    :param flags: Used `RpcMethodFlags`.
    :param access: Set the `RpcMethodAccess` level.
    :param signal: Signal name to be emitted. ``False`` means no signal
                   (default). ``True`` stands for ``chng`` signal to be emitted.
                   Finally, *a string* gives the signal's name.
    """
    def wrapper(fn: Callable) -> Callable:
        fn._shv = {
            "path": path,
            "name": name,
            "flags": flags,
            "access": access,
            "signal": signal,
        }
        return fn
    return wrapper


def describe_method(fn: Callable) -> RpcMethodDesc:
    """Describe ``fn`` based on the ``fn._shv`` and ``fn``'s annotation.

    The result is stored in ``._shv_method_desc`` to be later used by the
    ``._dir`` method.

    This should now use https://silicon-heaven.github.io/shv-doc/rpctypes.html
    """
    extra = {}
    if fn.__doc__:
        extra["description"] = fn.__doc__

    param = "Null"
    for v in (v for k, v in fn.__annotations__.items()
              if k != "return"):
        param = repr(v)

    result = "Null"
    if "return" in fn.__annotations__:
        result = repr(fn.__annotations__["return"])

    signal = fn._shv["signal"]
    signals = {"chng" if signal is True else signal
               : result} if signal else {}

    name = fn._shv["name"]
    flags = fn._shv["flags"]
    access = fn._shv["access"]

    match name:
        case "get":
            flags = RpcMethodFlags.GETTER
            access = RpcMethodAccess.READ
        case "set":
            if signals != {}:
                raise AttributeError("Set signals for properties in getter!")
            flags = RpcMethodFlags.SETTER
            access = RpcMethodAccess.WRITE

    match flags, access, param, result:  # Check if getter or setter
        case None, None, "Null", "Null":
            pass
        case None, None, "Null", _:  # Expect getter
            flags = RpcMethodFlags.GETTER
            access = RpcMethodAccess.READ
        case None, None, _, "Null":  # Expect setter
            # It could be "Null" | "None" to apply for, e.g., reset
            flags = RpcMethodFlags.SETTER
            access = RpcMethodAccess.WRITE

    if flags is None:
        flags = RpcMethodFlags(0)

    if access is None:
        access = RpcMethodAccess.BROWSE

    return RpcMethodDesc(
        name=name,
        flags=flags,
        param=param,
        result=result,
        access=access,
        signals=signals,
        extra=extra,
    )


class SHVMethods(SHVBase):
    """Extend ``SHVBase`` with SHV method decorators."""

    def __init__(
        self,
        *args: Any,  # noqa ANN401
        **kwargs: Any,  # noqa ANN401
    ) -> None:
        self._end_app_fn: dict[
            str,  # SHV path
            dict[
                str,  # SHV method name
                Callable  # End-application function with _shv attr.
        ]] = defaultdict(dict)
        """Store end-application functions related to SHV."""

        self._shv_method_desc: dict[
            str,  # SHV path
            dict[
                str,  # SHV method name
                RpcMethodDesc  # SHV method description
        ]] = defaultdict(dict)
        """Store SHV method descriptions for given path, method name."""

        for a in (i for i in dir(self)
                  if hasattr(getattr(self, i), "_shv")):
            fn = getattr(self, a)
            path = fn._shv["path"]
            name = fn._shv["name"]
            self._end_app_fn[path][name] = fn
            self._shv_method_desc[path][name] = describe_method(fn)

        super().__init__(*args, **kwargs)

    def _ls(self, path: str) -> Iterator[str]:
        yield from super()._ls(path)
        if path:
            path = f"{path}/"
        yield from [full_path[len(path):].partition("/")[0]
                    for full_path in filter(
                        lambda p: p.startswith(path),
                        self._shv_method_desc.keys())]

    def _dir(self, path: str) -> Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        if path in self._shv_method_desc:
            yield from [md for md in self._shv_method_desc[path].values()]

    async def _method_call(self, req: SHVClient.Request) -> SHVType:
        async def _execute_fn(path: str, method: str) -> SHVType:
            """Execute ``fn`` described by ``path`` and ``method``.

            This auxilliary function detects how many parameters ``fn`` requires
            and calls ``fn`` with appropriate arguments, returning the result.

            When a SHV property is "set" and there is a signal set on the
            property's "get", we need yet to execute "get" and signal the
            result. The only reason for this auxilliary function is to DRY.
            """
            fn = self._end_app_fn[path][method]
            fn_params = [v for k, v in fn.__annotations__.items()
                         if k != "return"]
            match len(fn_params), req.param, req.user_id:
                case 0, _, _:
                    res = fn()
                case 1, None, None:
                    raise ValueError(
                        "Called fn needs a single argument,"
                        " but neither req.param nor req.user_id"
                        " is set.")
                case 1, None, _:
                    res = fn(req.user_id)
                case 1, _, _:
                    res = fn(req.param)
                case 2, _, _:
                    res = fn(req.param, req.user_id)
                case _:
                    raise NotImplementedError
            if asyncio.iscoroutine(res):
                res = await res
            return res

        if (req.path in self._shv_method_desc
            and req.method in self._shv_method_desc[req.path]
            and req.access >= self._shv_method_desc[req.path][req.method].access
        ):
            md = self._shv_method_desc[req.path][req.method]
            if (RpcMethodFlags.USER_ID_REQUIRED in md.flags
                and req.user_id is None
            ):
                raise RpcUserIDRequiredError
            else:
                res = await _execute_fn(req.path, req.method)
                # For a property node, signal is set on "get" but signaled on
                # "set" method. So when we processed "set" method and there
                # exists a corresponding "get" method where signal is set, we
                # need to signal the result of "get".
                res_get = None
                if (req.method == "set"
                    and "get" in self._shv_method_desc[req.path]
                    and self._shv_method_desc[req.path]["get"].signals != {}
                    and self._shv_method_desc[req.path]["set"].signals == {}
                ):
                    md = self._shv_method_desc[req.path]["get"]
                    res_get = await _execute_fn(req.path, "get")
                for signal in md.signals:
                    await self._signal(
                        path=req.path,
                        name="chng" if signal is True else signal,
                        source=md.name,
                        value=res_get if res_get is not None else res,
                        access=md.access,
                        user_id=req.user_id,
                    )
                return res
        else:
            return await super()._method_call(req)

    async def send_signal(
        self,
        path: str,
        method: str,
        value: SHVType | None = None
    ) -> None:
        """Send signal calling instance.

        :param path: Signal's node path.
        :param method: Signal's source method.
        :param value: Value to be sent. If ``None`` (default,) first call
                      ``self._end_app_fn[path][method]`` and use the result
                      as the value.
        """
        if value is None:
            # TODO may fail when fn needs arguments. This was solved by
            # auxilliary function _execute_fn in _method_call.
            value = self._end_app_fn[path][method]()
            if asyncio.iscoroutine(value):
                value = await value
        md = self._shv_method_desc[path][method]
        for signal in md.signals:
            await self._signal(
                path=path,
                name="chng" if signal is True else signal,
                source=md.name,
                value=value,
                access=md.access)
            print(f"just sent {value} as signal {signal} of {path} {method}")

    async def send_signal_by_fn(self, fn: Callable) -> None:
        """Send signal corresponding to the method ``fn``."""
        print("identified by fn: ", end="")
        await self.send_signal(fn._shv["path"], fn._shv["name"])


class ExampleDevice(SHVClient, SHVMethods):
    """Example device for testing purposes.

    This (non-hardware) device provides two root nodes and multiple "track"
    nodes:
    - property `numberOfTracks` with methods:
        - `get`
        - `set`
    - node `track` which has property subnodes (1..8 by default) with methods:
        - `lastResetUser`
        - `reset`

        and each subnode has methods:
        - `get`
        - `set`
    """

    APP_NAME = "ed"

    def __init__(
        self,
        *args: Any,  # noqa ANN401
        **kwargs: Any,  # noqa ANN401
    ) -> None:
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
        self.last_reset_user: str | None = None
        super().__init__(*args, **kwargs)

    @shv_method("numberOfTracks", "get", signal=True)
    def get_number_of_tracks(self) -> int:
        """Return number of tracks."""
        return len(self.tracks)

    @shv_method("numberOfTracks", "set")
    async def set_number_of_tracks(self, n: int) -> None:
        """Set number of tracks to ``n``."""
        if n < 1:
            raise ValueError("At least 1 track needed.")
        oldlen = len(self.tracks)
        if oldlen != n:
            new_tracks = {str(i): list(range(i)) for i in range(1, n + 1)}
            self.tracks = new_tracks | {
                    k: v for k, v in self.tracks.items() if int(k) <= n}
            # We changed track's nodes, so signal "lsmod".
            await self._lsmod(
                "track",
                {str(i): oldlen < n
                 for i in range(min(oldlen, n), max(oldlen, n))})

    @shv_method("track", "lastResetUser")
    def get_last_reset_user(self) -> str | None:
        """Return the user who reseted the tracks as the last one."""
        return self.last_reset_user

    @shv_method(
        path="track",
        name="reset",
        flags=RpcMethodFlags.USER_ID_REQUIRED,
        access=RpcMethodAccess.COMMAND)
    async def reset_tracks(self, by: str) -> None:
        """Reset all the tracks ``by`` to their default values."""
        self.last_reset_user = by
        old = self.tracks
        self.tracks = {str(i): list(range(i)) for i in range(1, 9)}
        # "get" and "set" for tracks is implemented manually (overriden _ls,
        # _dir, and _method_call). Therefore, we need to implement signals for
        # these methods manually, too.
        for ((old_k, old_v), new_v) in zip(
            old.items(), self.tracks.values(), strict=False
        ):
            if old_v != new_v:
                await self._signal(
                    path=f"track/{old_k}",
                    value=new_v)
        # We also potentially change nodes, so signal "lsmod" when appropriate.
        oldlen = len(old)
        newlen = len(self.tracks)
        if oldlen != newlen:
            minlen = min(oldlen, newlen)
            maxlen = max(oldlen, newlen)
            await self._lsmod(
                "track",
                {str(i): oldlen < newlen
                 for i in range(minlen, maxlen)})

    def get_track(self, k: str) -> list:
        """Return track ``k``."""
        return self.tracks[k]

    def set_track(self, k: str, v: list) -> None:
        """Set track ``k`` to value ``v``."""
        self.tracks[k] = v

    def _ls(self, path: str) -> Iterator[str]:
        yield from super()._ls(path)
        yield from self._ls_node_for_path(
            path,
            [f"track/{i}" for i in self.tracks.keys()])

    def _dir(self, path: str) -> Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        match path.split("/"):
            case ["track", track] if track in self.tracks:
                yield RpcMethodDesc.getter(
                    result="[i]",
                    description="List of tracks",
                    signal=True)
                yield RpcMethodDesc.setter(
                    param="[i]",
                    description="Set track")

    async def _method_call(self, req: SHVBase.Request) -> SHVType:
        match req.path.split("/"), req.method:
            case [["track", track], "get"] if req.access >= RpcMethodAccess.READ:
                return self.get_track(track)
            case [["track", track], "set"] if req.access >= RpcMethodAccess.WRITE:
                if not isinstance(req.param, list) or not all(
                    isinstance(v, int) for v in req.param
                ):
                    raise RpcInvalidParamError("Only list of ints is accepted.")
                old = self.get_track(track)
                self.set_track(track, req.param)
                if old != self.get_track(track):
                    await self._signal(
                        path=f"track/{track}",
                        value=self.get_track(track))
                return None
        return await super()._method_call(req)


async def loop_send_signal_1(c: ExampleDevice) -> None:
    """Loop sending signal."""
    while True:
        await c.send_signal("numberOfTracks", "get")
        await asyncio.sleep(2.0)


async def loop_send_signal_2(c: ExampleDevice) -> None:
    """Loop sending signal."""
    while True:
        await c.send_signal_by_fn(c.get_number_of_tracks)
        await asyncio.sleep(2.0)


async def run_example_device(url: str) -> None:
    """Coroutine that starts SHV and waits..."""
    client = await ExampleDevice.connect(RpcUrl.parse(url))
    if client is not None:
        await asyncio.gather(
            client.task,
            loop_send_signal_1(client),
            loop_send_signal_2(client))
        await client.disconnect()


def parse_args() -> argparse.Namespace:
    """Parse passed arguments and return result."""
    parser = argparse.ArgumentParser(description="Silicon Heaven example client")
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
        default="tcp://test@localhost?password=test",
        help="SHV RPC URL specifying connection to the broker.",
    )
    return parser.parse_args()


LOG_LEVELS = (
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
)


if __name__ == "__main__":
    # The original __main__ from the original example:
    args = parse_args()
    logging.basicConfig(
        level=LOG_LEVELS[sorted(
            [1 - args.v + args.q, 0, len(LOG_LEVELS) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )
    asyncio.run(run_example_device("tcp://test@localhost?password=test&devmount=test/ed"))
