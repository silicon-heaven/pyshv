"""Check that we correctly parse and serialize our URL format."""
import re

import pytest

from shv import RpcLoginType, RpcProtocol, RpcUrl

DATA = [
    ("unix:/dev/null", RpcUrl("/dev/null", protocol=RpcProtocol.UNIX)),
    (
        "unixs:/dev/null?user=test&password=foo",
        RpcUrl(
            "/dev/null", protocol=RpcProtocol.UNIXS, username="test", password="foo"
        ),
    ),
    (
        "serial:/dev/null?user=test%40example.com&password=a%C4%8D%C5%A1f",
        RpcUrl(
            "/dev/null",
            protocol=RpcProtocol.SERIAL,
            username="test@example.com",
            password="ačšf",
        ),
    ),
    ("tcp://test@localhost:4242", RpcUrl("localhost", username="test", port=4242)),
    (
        "ssl://test@localhost:4242",
        RpcUrl("localhost", protocol=RpcProtocol.SSL, username="test", port=4242),
    ),
    (
        "tcp://localhost:4242?devid=foo&devmount=/dev/null",
        RpcUrl("localhost", port=4242, device_id="foo", device_mount_point="/dev/null"),
    ),
    (
        "tcp://localhost:4242?devid=foo&devmount=/dev/null&password=test",
        RpcUrl(
            "localhost",
            port=4242,
            password="test",
            login_type=RpcLoginType.PLAIN,
            device_id="foo",
            device_mount_point="/dev/null",
        ),
    ),
    (
        "tcp://localhost:4242?devid=foo&devmount=/dev/null&shapass=" + ("x" * 40),
        RpcUrl(
            "localhost",
            port=4242,
            password="x" * 40,
            login_type=RpcLoginType.SHA1,
            device_id="foo",
            device_mount_point="/dev/null",
        ),
    ),
    ("tcp://[::]:4242", RpcUrl("::", port=4242)),
    ("serial:/dev/ttyX", RpcUrl("/dev/ttyX", protocol=RpcProtocol.SERIAL)),
    (
        "serial:/dev/ttyX?baudrate=1152000",
        RpcUrl("/dev/ttyX", protocol=RpcProtocol.SERIAL, baudrate=1152000),
    ),
]


@pytest.mark.parametrize("url,rpcurl", DATA)
def test_to_url(url, rpcurl):
    """Check that we correctly parse these URLs."""
    assert rpcurl.to_url() == url


@pytest.mark.parametrize(
    "url,rpcurl",
    DATA
    + [
        ("", RpcUrl("", protocol=RpcProtocol.UNIX)),
        ("/dev/null", RpcUrl("/dev/null", protocol=RpcProtocol.UNIX)),
        ("//dev/null", RpcUrl("/dev/null", protocol=RpcProtocol.UNIX)),
        (
            "unix://dev/null",
            RpcUrl("/dev/null", protocol=RpcProtocol.UNIX),
        ),
        ("tcp://localhost", RpcUrl("localhost", port=3755, protocol=RpcProtocol.TCP)),
        ("tcps://localhost", RpcUrl("localhost", port=3765, protocol=RpcProtocol.TCPS)),
        ("ssl://localhost", RpcUrl("localhost", port=3756, protocol=RpcProtocol.SSL)),
        ("ssls://localhost", RpcUrl("localhost", port=3766, protocol=RpcProtocol.SSLS)),
        ("tcp://test@localhost:4242", RpcUrl("localhost", username="test", port=4242)),
        ("tcp://localhost?devid=foo", RpcUrl("localhost", device_id="foo")),
    ],
)
def test_parse(url, rpcurl):
    """Check that we correctly parse these URLs."""
    assert RpcUrl.parse(url) == rpcurl


@pytest.mark.parametrize(
    "url,msg",
    (
        ("tcp://localhost?missing=some", "Unsupported URL queries: missing"),
        (
            "tcp://localhost?missing=some&other=foo",
            "Unsupported URL queries: missing, other",
        ),
        ("tcp:///dev/null", "Path is not supported for tcp: /dev/null"),
    ),
)
def test_invalid(url, msg):
    with pytest.raises(ValueError, match=re.escape(msg)):
        RpcUrl.parse(url)
