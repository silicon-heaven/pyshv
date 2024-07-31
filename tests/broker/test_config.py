"""Broker configuration loading."""

import pytest

from shv import RpcLogin, RpcLoginType, RpcMethodAccess, RpcProtocol, RpcUrl
from shv.broker import RpcBrokerConfig


def test_config(config):
    assert config == RpcBrokerConfig(
        name="testbroker",
        listen=[
            RpcUrl("localhost", 3755, RpcProtocol.TCP),
            RpcUrl("shvbroker.sock", protocol=RpcProtocol.UNIX),
        ],
        roles=[
            RpcBrokerConfig.Role(
                "admin",
                {"**"},
                {RpcMethodAccess.DEVEL: {"**:*"}},
            ),
            RpcBrokerConfig.Role(
                "test", {"test/*"}, {RpcMethodAccess.COMMAND: {"test/**:*"}}
            ),
            RpcBrokerConfig.Role(
                "browse",
                access={RpcMethodAccess.BROWSE: {"**:ls", "**:dir"}},
            ),
            RpcBrokerConfig.Role("nobody"),
        ],
        users=[
            RpcBrokerConfig.User("admin", "admin!123", ["admin"]),
            RpcBrokerConfig.User(
                "shaadmin",
                "57a261a7bcb9e6cf1db80df501cdd89cee82957e",
                ["admin"],
                RpcLoginType.SHA1,
            ),
            RpcBrokerConfig.User("test", "test", ["test", "browse"]),
            RpcBrokerConfig.User("nobody", "nobody", ["nobody"]),
        ],
        autosetups=[
            RpcBrokerConfig.Autosetup(
                {"history"}, {"admin"}, ".history", {"test/**:*:*"}
            ),
            RpcBrokerConfig.Autosetup({"?*"}, {"admin", "test"}, "test/%d%i"),
        ],
    )


def test_subconfig(subconfig):
    assert subconfig == RpcBrokerConfig(
        listen=[
            RpcUrl("shvsubbroker.sock", protocol=RpcProtocol.UNIX),
        ],
        connect=[
            RpcBrokerConfig.Connect(
                RpcUrl(
                    "localhost",
                    login=RpcLogin(
                        "test",
                        "test",
                        options={"device": {"mountPoint": "test/subbroker"}},
                    ),
                ),
                ["upper"],
                "..",
            )
        ],
        roles=[
            RpcBrokerConfig.Role("admin", {"**"}, {RpcMethodAccess.DEVEL: {"**:*"}}),
            RpcBrokerConfig.Role("upper", access={RpcMethodAccess.COMMAND: {"**:*"}}),
        ],
        users=[
            RpcBrokerConfig.User("admin", "admin!234", ["admin"]),
        ],
    )


def test_login_valid_admin(config):
    role = config.login(RpcLogin("admin", "admin!123"), "nonce")
    assert role is not None
    assert role.user is config.users["admin"]


def test_login_valid_test(config):
    role = config.login(RpcLogin("test", "test"), "nonce")
    assert role is not None
    assert role.user is config.users["test"]


def test_login_invalid(config):
    assert config.login(RpcLogin("test", "invalid"), "nonce") is None


def test_login_invalid_mount(config):
    with pytest.raises(ValueError):
        config.login(
            RpcLogin("test", "test", opt_device_mount_point="toplevel"), "nonce"
        )


@pytest.mark.parametrize(
    "path,method,res",
    (
        ("", "ls", RpcMethodAccess.BROWSE),
        ("", "get", None),
        ("test/device/track/1", "get", RpcMethodAccess.COMMAND),
    ),
)
def test_access_level_test(config, path, method, res):
    role = config.login(RpcLogin("test", "test"), "nonce")
    assert role.access_level(path, method) == res


def test_role_test(config):
    role = config.login(RpcLogin("test", "test"), "nonce")
    assert role.name == "test-browse"
    assert role.mount_point(set()) is None
    assert list(role.initial_subscriptions()) == []


def test_role_test_mount_point(config):
    role = config.login(
        RpcLogin("test", "test", opt_device_mount_point="test/some"), "nonce"
    )
    assert role.mount_point(set()) == "test/some"


def test_role_test_device_id(config):
    role = config.login(RpcLogin("test", "test", opt_device_id="some"), "nonce")
    assert role.mount_point(set()) == "test/some"
    assert role.mount_point({"test/some"}) == "test/some1"
    assert role.mount_point({"test/some1"}) == "test/some"
    assert role.mount_point({"test/some", "test/some1"}) == "test/some2"
    assert list(role.initial_subscriptions()) == []


def test_role_history(config):
    role = config.login(
        RpcLogin("admin", "admin!123", opt_device_id="history"), "nonce"
    )
    assert role.mount_point(set()) == ".history"
    # assert role.mount_point({".history"}) is None  # TODO
    assert list(role.initial_subscriptions()) == ["test/**:*:*"]


@pytest.mark.parametrize(
    "path,method,res",
    (
        ("", "ls", RpcMethodAccess.COMMAND),
        ("test/device/track/1", "get", RpcMethodAccess.COMMAND),
    ),
)
def test_access_level_upper(subconfig, path, method, res):
    url, role = next(subconfig.connections())
    assert url is subconfig.connect[0].url
    assert role.connection is subconfig.connect[0]
    assert role.access_level(path, method) == res


def test_upper(subconfig):
    _, role = next(subconfig.connections())
    assert role.name == "upper"
    assert role.mount_point(set()) == ".."
    # assert role.mount_point({".."}) is None  # TODO
    assert list(role.initial_subscriptions()) == []


@pytest.mark.parametrize(
    "mntfmt,existing,expected",
    (
        (".history", {"test/one", "test/two"}, ".history"),
        (".history", {"test/one", ".history"}, None),
        ("test/%d%i", {".history"}, "test/devid"),
        ("test/%d%i", {".history", "test/devid", "test/devid1"}, "test/devid2"),
        ("%Idyn/fo%i%Io", {"0dyn/fo0o", "1dyn/fo11o"}, "2dyn/fo22o"),
        ("%%%/%foo", set(), "%%/%foo"),
        ("%r/%u", set(), "r1-r2/admin"),
    ),
)
def test_autosetup(mntfmt, existing, expected):
    autosetup = RpcBrokerConfig.Autosetup(set(), mount_point=mntfmt)
    user = RpcBrokerConfig.User("admin", "admin!123", ["r1", "r2"])
    assert autosetup.generate_mount_point(existing, "devid", user) == expected
