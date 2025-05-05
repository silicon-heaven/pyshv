"""Check the behavior of the SHVBase."""

import asyncio
import collections.abc
import logging

import pytest

from shv import (
    SHV_VERSION,
    RpcDir,
    RpcInvalidParamError,
    RpcMessage,
    RpcRequestInvalidError,
    RpcTryAgainLaterError,
    RpcUserIDRequiredError,
    SHVBase,
    SHVType,
)
from shv.rpctransport import RpcClientPipe

logger = logging.getLogger(__name__)


class App(SHVBase):
    """The SHV application used in these tests."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.event = asyncio.Event()
        self.cancelled = False

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        match request.path, request.method:
            case "test", "delay":
                for i in range(4):
                    request.progress = 1.0 / 4 * i
                    await asyncio.sleep(0.01)
                return None
            case "test", "delay-event":
                try:
                    await self.event.wait()
                    request.progress = 0.42
                    self.event.clear()
                    await self.event.wait()
                    return None
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise
        return await super()._method_call(request)

    def _ls(self, path: str) -> collections.abc.Iterator[str]:
        if not path:
            yield "test"
        yield from super()._ls(path)

    def _dir(self, path: str) -> collections.abc.Iterator[RpcDir]:
        if path == "test":
            yield RpcDir("delay")
            yield RpcDir("delay-event")
        yield from super()._dir(path)


@pytest.fixture(name="con")
async def fixture_con():
    """Pair of raw client and SHVBase."""
    client1, client2 = await RpcClientPipe.open_pair()
    shv = App(client2, peer_shv_version=SHV_VERSION)
    yield shv, client1
    client1.disconnect()
    await shv.disconnect()
    await client1.wait_disconnect()


async def test_req_ping(con):
    msg = RpcMessage.request(".app", "ping")
    await con[1].send(msg)
    assert await con[1].receive() == msg.make_response()


async def test_delay(con):
    """Check that we report progress on our own."""
    msg = RpcMessage.request("test", "delay")
    await con[1].send(msg)
    assert await con[1].receive() == msg.make_response_delay(0.0)
    assert await con[1].receive() == msg.make_response_delay(0.25)
    assert await con[1].receive() == msg.make_response_delay(0.5)
    assert await con[1].receive() == msg.make_response_delay(0.75)
    assert await con[1].receive() == msg.make_response()


async def test_delay_event(con):
    """Check that we can query the delayed task."""
    msg = RpcMessage.request("test", "delay-event")
    await con[1].send(msg)
    await con[1].send(msg.make_abort(False))
    assert await con[1].receive() == msg.make_response_delay(0.0)
    con[0].event.set()
    assert await con[1].receive() == msg.make_response_delay(0.42)
    await con[1].send(msg.make_abort(False))
    assert await con[1].receive() == msg.make_response_delay(0.42)
    con[0].event.set()
    assert await con[1].receive() == msg.make_response()


async def test_delay_event_abort(con):
    """Check that we can query the delayed task."""
    msg = RpcMessage.request("test", "delay-event")
    await con[1].send(msg)
    con[0].event.set()
    assert await con[1].receive() == msg.make_response_delay(0.42)
    assert not con[0].cancelled
    await con[1].send(msg.make_abort(True))
    assert await con[1].receive() == msg.make_response(
        RpcRequestInvalidError("Request cancelled")
    )
    assert con[0].cancelled


async def test_call_ping(con):
    """Check that we correctly simple call sequence."""
    task = asyncio.create_task(con[0].ping())
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        ".app", "ping", None, RpcMessage.next_request_id() - 1
    )
    await con[1].send(msg.make_response())
    assert await task is None


async def test_call_error(con):
    """Check that we propagate error."""
    task = asyncio.create_task(con[0].call("test", "error"))
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        "test", "error", None, RpcMessage.next_request_id() - 1
    )
    await con[1].send(msg.make_response(RpcInvalidParamError("text")))
    with pytest.raises(RpcInvalidParamError, match=r"text"):
        await task


async def test_call_delay(con):
    """Check that we can call delayed requests."""
    reported = []
    task = asyncio.create_task(
        con[0].call("test", "delay", query_timeout=0.01, progress=reported.append)
    )
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        "test", "delay", None, RpcMessage.next_request_id() - 1
    )
    await con[1].send(msg.make_response_delay(0.2))
    await con[1].send(msg.make_response_delay(0.3))
    assert await con[1].receive() == msg.make_abort(False)
    await con[1].send(msg.make_response())
    assert await task is None
    assert reported == [0.2, 0.3]


async def test_call_lost(con):
    """Check that we send request again as soon as lost is detected."""
    task = asyncio.create_task(con[0].call("test", "lost", query_timeout=0.01))
    msg = await con[1].receive()
    rid = RpcMessage.next_request_id() - 1
    assert msg == RpcMessage.request("test", "lost", None, rid)
    await con[1].send(msg.make_response(RpcRequestInvalidError("Lost")))
    assert await con[1].receive() == RpcMessage.request("test", "lost", None, rid)
    await con[1].send(msg.make_response("value"))
    assert await task == "value"


async def test_call_reset(con):
    """Check that we will recover call after reset."""
    task = asyncio.create_task(con[0].call("test", "withreset"))
    msg = await con[1].receive()
    rid = RpcMessage.next_request_id() - 1
    assert msg == RpcMessage.request("test", "withreset", None, rid)
    await con[1].reset()
    msg = await con[1].receive()
    assert msg == RpcMessage.request("test", "withreset", None, rid)
    await con[1].send(msg.make_response(42))
    assert await task == 42


async def test_call_user_id_required(con):
    """Check that we are able to fill in the user ID."""
    con[0].user_id = "foo"
    task = asyncio.create_task(con[0].call("test", "foruserid"))
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        "test", "foruserid", None, RpcMessage.next_request_id() - 1
    )
    await con[1].send(msg.make_response(RpcUserIDRequiredError()))
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        "test", "foruserid", None, RpcMessage.next_request_id() - 1, user_id="foo"
    )
    await con[1].send(msg.make_response(msg.user_id))
    assert await task == "foo"


async def test_call_try_again_later(con):
    """Check that we are able to delay our request after try again later error."""
    task = asyncio.create_task(con[0].call("test", "again", retry_timeout=0.05))
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        "test", "again", None, RpcMessage.next_request_id() - 1
    )
    await con[1].send(msg.make_response(RpcTryAgainLaterError()))
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        "test", "again", None, RpcMessage.next_request_id() - 1
    )
    await con[1].send(msg.make_response(42))
    assert await task == 42


async def test_call_abort(con):
    """Check that we are able to delay our request after try again later error."""
    task = asyncio.create_task(con[0].call("test", "abort"))
    msg = await con[1].receive()
    assert msg == RpcMessage.request(
        "test", "abort", None, RpcMessage.next_request_id() - 1
    )
    task.cancel()
    assert await con[1].receive() == msg.make_abort(True)
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_call_old(con):
    """Check that we can manage old calls if message is lost."""
    task = asyncio.create_task(con[0].call("test", "old", retry_timeout=0.05))
    msg = await con[1].receive()
    rid = RpcMessage.next_request_id() - 1
    assert msg == RpcMessage.request("test", "old", None, rid)
    assert await con[1].receive() == msg
    await con[1].send(msg.make_response(0))
    assert await task == 0
