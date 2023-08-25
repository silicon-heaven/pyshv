"""Check various clients implementing a different link layers.
"""
import asyncio
import io
import os
import pty
import select
import threading

import pytest
import serial

from shv import (
    RpcClient,
    RpcClientDatagram,
    RpcClientSerial,
    RpcClientStream,
    RpcErrorCode,
    RpcInvalidRequestError,
    RpcMessage,
    RpcServerDatagram,
    RpcServerStream,
)


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
        msg.set_shverror(RpcErrorCode.INVALID_REQUEST, "Fake error")
        await clients[0].send(msg)
        assert await clients[1].receive(False) == msg

    async def test_error_raise(self, clients):
        msg = RpcMessage.request(".app", "dir").make_response()
        msg.set_shverror(RpcErrorCode.INVALID_REQUEST, "Fake error")
        await clients[0].send(msg)
        with pytest.raises(RpcInvalidRequestError):
            await clients[1].receive(True)

    async def test_eof(self, clients):
        await clients[0].disconnect()
        assert await clients[1].receive() is None

    async def test_invalid_reset(self, clients):
        await clients[0].disconnect()
        with pytest.raises(
            RuntimeError, match="^Reset can be called only on connected client.$"
        ):
            await clients[0].reset()


class ServerLink(Link):
    async def test_reset_client(self, clients, server):
        await clients[1].reset()
        server_client = await server[1].get()
        msg = RpcMessage.request("foo", "ls")
        await clients[1].send(msg)
        assert await server_client.receive() == msg


class Stream(ServerLink):
    async def test_reset_server_client(self, clients):
        await clients[0].reset()
        assert not clients[0].connected()


class TestTCP(Stream):
    """Check that TCP/IP transport protocol works."""

    @pytest.fixture(name="server")
    async def fixture_server(self, port):
        queue = asyncio.Queue()
        server = await RpcServerStream.listen(queue.put, "localhost", port)
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, port):
        client = await RpcClientStream.connect("localhost", port)
        server_client = await server[1].get()
        yield server_client, client
        await server_client.disconnect()
        await client.disconnect()


class TestUnix(Stream):
    """Check that Unix transport protocol works."""

    @pytest.fixture(name="sockpath")
    def fixture_sockpath(self, tmp_path):
        return tmp_path / "shv.sock"

    @pytest.fixture(name="server")
    async def fixture_server(self, sockpath):
        queue = asyncio.Queue()
        server = await RpcServerStream.unix_listen(queue.put, sockpath)
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, sockpath):
        client = await RpcClientStream.unix_connect(sockpath)
        server_client = await server[1].get()
        yield server_client, client
        await server_client.disconnect()
        await client.disconnect()


class TestUDP(Link):
    """Check that UDP/IP transport protocol works."""

    @pytest.fixture(name="server")
    async def fixture_server(self, port):
        queue = asyncio.Queue()
        server = await RpcServerDatagram.listen(queue.put, "localhost", port)
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, port):
        client = await RpcClientDatagram.connect("localhost", port)
        await client.reset()
        res = await server[1].get()
        yield res, client
        await res.disconnect()
        await client.disconnect()

    @pytest.mark.skip("Disconnect can't be propagated over UDP")
    async def test_eof(self, a: RpcClient, b: RpcClient):
        pass


class TestSerial(Link):
    """Check that we can work over Serial port transport protocol."""

    @pytest.fixture(name="clients")
    async def fixture_clients(self):
        pty1_master, pty1_slave = pty.openpty()
        pty2_master, pty2_slave = pty.openpty()
        task = threading.Thread(target=self.ptycopy, args=(pty1_master, pty2_master))
        task.start()

        client1 = await RpcClientSerial.open(os.ttyname(pty1_slave))
        os.close(pty1_slave)
        client2 = await RpcClientSerial.open(os.ttyname(pty2_slave))
        os.close(pty2_slave)

        yield client1, client2

        await client1.disconnect()
        await client2.disconnect()
        task.join()

    def ptycopy(self, fd1, fd2):
        p = select.poll()
        p.register(fd1, select.POLLIN | select.POLLPRI)
        p.register(fd2, select.POLLIN | select.POLLPRI)
        while True:
            for fd, event in p.poll():
                if event & select.POLLIN:
                    data = os.read(fd, io.DEFAULT_BUFFER_SIZE)
                    os.write(fd1 if fd is fd2 else fd2, data)
                if event & select.POLLHUP or event & select.POLLERR:
                    os.close(fd1)
                    os.close(fd2)
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
