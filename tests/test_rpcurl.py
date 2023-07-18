"""Check that we correctly parse and serialize our URL format."""
import pytest

from shv import RpcLoginType, RpcProtocol, RpcUrl

DATA = [
    ("localsocket:/dev/null", RpcUrl("/dev/null", protocol=RpcProtocol.LOCAL_SOCKET)),
    ("tcp://test@localhost:4242", RpcUrl("localhost", username="test", port=4242)),
    (
        "udp://test@localhost:4242",
        RpcUrl("localhost", protocol=RpcProtocol.UDP, username="test", port=4242),
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
        "tcp://localhost:4242?devid=foo&devmount=/dev/null&shapass=xxxxxxxx",
        RpcUrl(
            "localhost",
            port=4242,
            password="xxxxxxxx",
            login_type=RpcLoginType.SHA1,
            device_id="foo",
            device_mount_point="/dev/null",
        ),
    ),
    ("tcp://[::]:4242", RpcUrl("::", port=4242)),
]


@pytest.mark.parametrize(
    "url,rpcurl",
    DATA
    + [
        ("", RpcUrl("", protocol=RpcProtocol.LOCAL_SOCKET)),
        ("/dev/null", RpcUrl("/dev/null", protocol=RpcProtocol.LOCAL_SOCKET)),
        ("//dev/null", RpcUrl("/dev/null", protocol=RpcProtocol.LOCAL_SOCKET)),
        (
            "localsocket://dev/null",
            RpcUrl("/dev/null", protocol=RpcProtocol.LOCAL_SOCKET),
        ),
        ("tcp://localhost", RpcUrl("localhost")),
        ("tcp://test@localhost:4242", RpcUrl("localhost", username="test", port=4242)),
        ("tcp://localhost?devid=foo", RpcUrl("localhost", device_id="foo")),
    ],
)
def test_parse(url, rpcurl):
    """Check that we correctly parse these URLs."""
    assert RpcUrl.parse(url) == rpcurl


def test_invalid():
    with pytest.raises(ValueError):
        RpcUrl.parse("foo://some")


def test_invalid_query():
    with pytest.raises(ValueError):
        RpcUrl.parse("tcp:localhost?missing=some")


@pytest.mark.parametrize("url,rpcurl", DATA)
def test_to_url(url, rpcurl):
    """Check that we correctly parse these URLs."""
    assert rpcurl.to_url() == url
