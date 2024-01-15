"""Check various clients implementing a different link layers.
"""
import asyncio
import io
import logging
import multiprocessing
import os
import pty
import select

import pytest

from shv import (
    RpcClientPipe,
    RpcClientTCP,
    RpcClientTTY,
    RpcClientUnix,
    RpcInvalidRequestError,
    RpcMessage,
    RpcServerTCP,
    RpcServerUnix,
)

logger = logging.getLogger(__name__)


class Link:
    """Generic tests applied to link layers."""

    async def test_call(self, clients):
        msg = RpcMessage.request(".app", "dir")
        await clients[0].send(msg)
        assert await clients[1].receive() == msg

    async def test_notify(self, clients):
        msg = RpcMessage.chng(".app", None)
        await clients[1].send(msg)
        assert await clients[0].receive() == msg

    async def test_error_receive(self, clients):
        msg = RpcMessage.request(".app", "dir").make_response()
        msg.rpc_error = RpcInvalidRequestError("Fake error")
        await clients[0].send(msg)
        assert await clients[1].receive(False) == msg

    async def test_error_raise(self, clients):
        msg = RpcMessage.request(".app", "dir").make_response()
        msg.rpc_error = RpcInvalidRequestError("Fake error")
        await clients[0].send(msg)
        with pytest.raises(RpcInvalidRequestError):
            await clients[1].receive(True)


class ServerLink(Link):
    """Additional tests for server-client connections."""

    async def test_reset_client(self, clients, server):
        await clients[1].reset()
        server_client = await server[1].get()
        msg = RpcMessage.request("foo", "ls")
        await clients[1].send(msg)
        assert await server_client.receive() == msg
        server_client.disconnect()
        await server_client.wait_disconnect()

    async def test_reset_server_client(self, clients):
        assert not await clients[0].reset()
        assert not clients[0].connected

    @pytest.mark.parametrize("cdisc,crecv", ((0, 1), (1, 0)))
    async def test_eof(self, clients, cdisc, crecv):
        clients[cdisc].disconnect()
        await clients[cdisc].wait_disconnect()
        with pytest.raises(EOFError):
            await clients[crecv].receive()


class TestTCP(ServerLink):
    """Check that TCP/IP transport protocol works."""

    @pytest.fixture(name="server")
    async def fixture_server(self, port):
        queue = asyncio.Queue()
        server = RpcServerTCP(queue.put, "localhost", port)
        await server.listen()
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, port):
        client = await RpcClientTCP.connect("localhost", port)
        server_client = await server[1].get()
        yield server_client, client
        client.disconnect()
        server_client.disconnect()
        await client.wait_disconnect()
        await server_client.wait_disconnect()


class TestUnix(ServerLink):
    """Check that Unix transport protocol works."""

    @pytest.fixture(name="sockpath")
    def fixture_sockpath(self, tmp_path):
        return tmp_path / "s"

    @pytest.fixture(name="server")
    async def fixture_server(self, sockpath):
        queue = asyncio.Queue()
        server = RpcServerUnix(queue.put, sockpath)
        await server.listen()
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, sockpath):
        client = await RpcClientUnix.connect(sockpath)
        server_client = await server[1].get()
        yield server_client, client
        server_client.disconnect()
        client.disconnect()
        await server_client.wait_disconnect()
        await client.wait_disconnect()


class TestPipe(Link):
    """Check that we can work over Unix pipe pair."""

    @pytest.fixture(name="clients")
    async def fixture_clients(self):
        client1, client2 = await RpcClientPipe.open_pair()
        yield client1, client2
        client1.disconnect()
        client2.disconnect()
        await client1.wait_disconnect()
        await client2.wait_disconnect()


class TestSerial(Link):
    """Check that we can work over Serial port transport protocol."""

    @pytest.fixture(name="clients")
    async def fixture_clients(self):
        pty1_master, pty1_slave = pty.openpty()
        pty2_master, pty2_slave = pty.openpty()
        process = multiprocessing.Process(
            target=self.ptycopy, args=(pty1_master, pty2_master)
        )
        process.start()

        client1 = await RpcClientTTY.open(os.ttyname(pty1_slave))
        os.close(pty1_slave)
        client2 = await RpcClientTTY.open(os.ttyname(pty2_slave))
        os.close(pty2_slave)

        yield client1, client2

        client1.disconnect()
        client2.disconnect()
        await client1.wait_disconnect()
        await client2.wait_disconnect()
        process.terminate()
        process.join()

    def ptycopy(self, fd1, fd2):
        p = select.poll()
        p.register(fd1, select.POLLIN | select.POLLPRI)
        p.register(fd2, select.POLLIN | select.POLLPRI)
        while True:
            for fd, event in p.poll():
                if event & select.POLLIN:
                    data = os.read(fd, io.DEFAULT_BUFFER_SIZE)
                    os.write(fd1 if fd is fd2 else fd2, data)
                if event & select.POLLERR:
                    logger.error("Error detected in ptycopy")
                    return

    async def test_escapes(self, clients):
        msg = RpcMessage.request("prop", "set", b"1\xa2\xa3\xa4\xa5\xaa2")
        await clients[0].send(msg)
        assert await clients[1].receive() == msg

    async def test_reset_client(self, clients):
        # Note: both sides are the same so we can test only from one side to the other
        msg = RpcMessage.request("foo", "ls")
        await clients[0].send(msg)
        assert await clients[1].receive() == msg
        await clients[0].reset()
        await clients[0].send(msg)
        assert await clients[1].receive() == msg
