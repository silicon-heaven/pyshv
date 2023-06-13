"""Broker configuration loading."""
import configparser

import pytest

from shv import RpcLoginType, RpcMethodAccess, RpcUrl, broker


def test_listen(config):
    assert config.listen == {
        "internet": RpcUrl.parse("tcp://[::]:3755"),
        "unix": RpcUrl.parse("localsocket:shvbroker.sock"),
    }


RULE_ADMIN = broker.RpcBrokerConfig.Rule("admin", path="")
RULE_COM = broker.RpcBrokerConfig.Rule(
    "com", path=".broker/app", methods=frozenset(("ping", "echo"))
)
RULE_SIGNALS = broker.RpcBrokerConfig.Rule(
    "signals", path=".broker/app", methods=frozenset(("subscribe", "unsubscribe"))
)
RULE_TESTER = broker.RpcBrokerConfig.Rule("tester", path="test")
RULES = {
    RULE_ADMIN,
    RULE_COM,
    RULE_SIGNALS,
    RULE_TESTER,
}


def test_rules(config):
    assert set(config.rules()) == RULES


ROLE_ADMIN = broker.RpcBrokerConfig.Role(
    "admin",
    RpcMethodAccess.ADMIN,
    frozenset({RULE_ADMIN}),
)
ROLE_CLIENT = broker.RpcBrokerConfig.Role(
    "client",
    RpcMethodAccess.WRITE,
    frozenset({RULE_COM, RULE_SIGNALS}),
)
ROLE_TESTER = broker.RpcBrokerConfig.Role(
    "tester",
    RpcMethodAccess.COMMAND,
    frozenset({RULE_TESTER}),
    frozenset({ROLE_CLIENT}),
)
ROLES = {
    ROLE_ADMIN,
    ROLE_TESTER,
    ROLE_CLIENT,
}


def test_roles(config):
    assert set(config.roles()) == ROLES


USER_ADMIN = broker.RpcBrokerConfig.User(
    "admin", "admin!123", RpcLoginType.PLAIN, frozenset({ROLE_ADMIN})
)
USER_SHAADMIN = broker.RpcBrokerConfig.User(
    "shaadmin",
    "57a261a7bcb9e6cf1db80df501cdd89cee82957e",
    RpcLoginType.SHA1,
    frozenset({ROLE_ADMIN}),
)
USER_TEST = broker.RpcBrokerConfig.User(
    "test",
    "test",
    RpcLoginType.PLAIN,
    frozenset({ROLE_TESTER}),
)
USERS = {
    USER_ADMIN,
    USER_SHAADMIN,
    USER_TEST,
}


def test_users(config):
    assert set(config.users()) == USERS


def test_user(config):
    assert config.user("admin") == USER_ADMIN


def test_default_config():
    config = broker.RpcBrokerConfig.load(configparser.ConfigParser())
    assert config.listen == {}
    assert set(config.users()) == set()
    assert set(config.roles()) == set()
    assert set(config.rules()) == set()


def test_login_valid_admin(config):
    assert config.login("admin", "admin!123", "", RpcLoginType.PLAIN) == USER_ADMIN


def test_login_valid_admin_sha1(config):
    assert (
        config.login(
            "admin",
            "bcfb57d8e21225f47290e4fef8acae80b86f85ef",
            "12345678",
            RpcLoginType.SHA1,
        )
        == USER_ADMIN
    )


def test_login_valid_shaadmin(config):
    assert (
        config.login(
            "shaadmin",
            "bcfb57d8e21225f47290e4fef8acae80b86f85ef",
            "12345678",
            RpcLoginType.SHA1,
        )
        == USER_SHAADMIN
    )


def test_login_valid_test(config):
    assert config.login("test", "test", "", RpcLoginType.PLAIN) == USER_TEST


@pytest.mark.parametrize(
    "user,password,nonce,tp",
    (
        ("test", "invalid", "", RpcLoginType.PLAIN),
        ("admin", "admin", "", RpcLoginType.PLAIN),
        ("admin", "admin", "", RpcLoginType.SHA1),
        ("", "", "", RpcLoginType.PLAIN),
    ),
)
def test_login_invalid(config, user, password, nonce, tp):
    assert config.login(user, password, nonce, tp) is None


@pytest.mark.parametrize(
    "user,path,method,expected",
    (
        (USER_ADMIN, "any", "get", RpcMethodAccess.ADMIN),
        (USER_TEST, "any", "get", RpcMethodAccess.BROWSE),
        (USER_TEST, "test/device", "appName", RpcMethodAccess.COMMAND),
        (USER_TEST, "test/device/track/1", "get", RpcMethodAccess.COMMAND),
        (USER_TEST, ".broker/app", "subscribe", RpcMethodAccess.WRITE),
        (USER_TEST, ".broker/app", "unsubscribe", RpcMethodAccess.WRITE),
    ),
)
def test_access_level(user, path, method, expected):
    assert user.access_level(path, method) == expected
