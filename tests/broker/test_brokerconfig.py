"""Broker configuration loading."""
import configparser

import pytest

from shv import RpcLoginType, RpcMethodAccess, RpcUrl, broker


def test_listen(config):
    assert config.listen == {
        "internet": RpcUrl.parse("tcp://[::]:3755"),
        "unix": RpcUrl.parse("localsocket:shvbroker.sock"),
    }


RULE_ADMIN = broker.RpcBrokerConfig.Rule(
    "admin", path="", method="", level=RpcMethodAccess.ADMIN
)
RULE_PING = broker.RpcBrokerConfig.Rule(
    "ping", path=".broker/app", method="ping", level=RpcMethodAccess.READ
)
RULE_ECHO = broker.RpcBrokerConfig.Rule(
    "echo", path=".broker/app", method="echo", level=RpcMethodAccess.WRITE
)
RULE_SUBSCRIBE = broker.RpcBrokerConfig.Rule(
    "subscribe",
    path=".broker/app",
    method="subscribe",
    level=RpcMethodAccess.READ,
)
RULE_UNSUBSCRIBE = broker.RpcBrokerConfig.Rule(
    "unsubscribe",
    path=".broker/app",
    method="unsubscribe",
    level=RpcMethodAccess.READ,
)
RULE_TESTER = broker.RpcBrokerConfig.Rule(
    "tester", path="test", method="", level=RpcMethodAccess.WRITE
)
RULES = {
    RULE_ADMIN,
    RULE_PING,
    RULE_ECHO,
    RULE_SUBSCRIBE,
    RULE_UNSUBSCRIBE,
    RULE_TESTER,
}


def test_rules(config):
    assert set(config.rules()) == RULES


ROLE_ADMIN = broker.RpcBrokerConfig.Role(
    "admin",
    frozenset({RULE_ADMIN}),
)
ROLE_CLIENT = broker.RpcBrokerConfig.Role(
    "client",
    frozenset({RULE_PING, RULE_ECHO, RULE_SUBSCRIBE, RULE_UNSUBSCRIBE}),
)
ROLE_TESTER = broker.RpcBrokerConfig.Role(
    "tester",
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


def test_roles_in_role(config):
    assert set(config.role("tester")) == {
        RULE_TESTER,
        RULE_PING,
        RULE_ECHO,
        RULE_SUBSCRIBE,
        RULE_UNSUBSCRIBE,
    }


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
