"""Check implementation of :class:`RpcLogin`."""

import re

import pytest

from shv import RpcInvalidParamError, RpcLogin, RpcLoginType


def test_options_init():
    assert RpcLogin(opt_device_id="foo", opt_device_mount_point="test/foo").options == {
        "device": {"deviceId": "foo", "mountPoint": "test/foo"}
    }


def test_device_id():
    obj = RpcLogin()
    assert obj.device_id is None
    obj.device_id = "foo"
    assert obj.device_id == "foo"
    assert obj.options == {"device": {"deviceId": "foo"}}
    obj.device_id = None
    assert obj.device_id is None
    assert obj.options == {}


def test_device_mount_point():
    obj = RpcLogin(opt_device_id="foo")
    assert obj.device_mount_point is None
    obj.device_mount_point = "test/foo"
    assert obj.device_mount_point == "test/foo"
    assert obj.options == {"device": {"deviceId": "foo", "mountPoint": "test/foo"}}
    obj.device_mount_point = None
    assert obj.device_mount_point is None
    assert obj.options == {"device": {"deviceId": "foo"}}


def test_idle_timeout():
    obj = RpcLogin(opt_device_id="foo")
    assert obj.idle_timeout is None
    obj.idle_timeout = 300
    assert obj.idle_timeout == 300
    assert obj.options == {"device": {"deviceId": "foo"}, "idleWatchDogTimeOut": 300}
    obj.idle_timeout = None
    assert obj.idle_timeout is None
    assert obj.options == {"device": {"deviceId": "foo"}}


def test_extend_options():
    obj = RpcLogin(options={"foo": 42, "ord": {"left": "<"}, "wtf": {"this": 1}})
    obj.extend_options({"foo": 24, "ord": {"right": ">"}, "wtf": {"this": None}})
    assert obj.options == {"foo": 24, "ord": {"left": "<", "right": ">"}}


@pytest.mark.parametrize(
    "obj,password,login_type,expected",
    (
        (RpcLogin("admin"), "", RpcLoginType.PLAIN, True),
        (RpcLogin("admin"), "invalid", RpcLoginType.PLAIN, False),
        (
            RpcLogin(
                "admin", "a7162d463b28666737f63034db39f03bca59b060", RpcLoginType.SHA1
            ),
            "",
            RpcLoginType.PLAIN,
            True,
        ),
        (
            RpcLogin(
                "admin", "a7162d463b28666737f63034db39f03bca59b060", RpcLoginType.SHA1
            ),
            "invalid",
            RpcLoginType.PLAIN,
            False,
        ),
        (
            RpcLogin("admin"),
            "da39a3ee5e6b4b0d3255bfef95601890afd80709",
            RpcLoginType.SHA1,
            True,
        ),
        (
            RpcLogin("admin"),
            "81f344a7686a80b4c5293e8fdc0b0160c82c06a8",
            RpcLoginType.SHA1,
            False,
        ),
        (
            RpcLogin(
                "admin", "a7162d463b28666737f63034db39f03bca59b060", RpcLoginType.SHA1
            ),
            "81f344a7686a80b4c5293e8fdc0b0160c82c06a8",
            RpcLoginType.SHA1,
            False,
        ),
    ),
)
def test_validate_password(obj, password, login_type, expected):
    assert obj.validate_password(password, "nonce", login_type) is expected


@pytest.mark.parametrize(
    "obj,custom_options,trusted,shv",
    (
        (
            RpcLogin("admin", "admin!123"),
            None,
            True,
            {
                "login": {"password": "admin!123", "user": "admin", "type": "PLAIN"},
                "options": {},
            },
        ),
        (
            RpcLogin("admin", options={"device": {"mountPoint": "test/this"}}),
            {"other": 42, "device": {"deviceId": "foo"}},
            False,
            {
                "login": {
                    "password": "a7162d463b28666737f63034db39f03bca59b060",
                    "user": "admin",
                    "type": "SHA1",
                },
                "options": {
                    "device": {"deviceId": "foo", "mountPoint": "test/this"},
                    "other": 42,
                },
            },
        ),
    ),
)
def test_to_shv(obj, custom_options, trusted, shv):
    assert obj.to_shv("nonce", custom_options, trusted) == shv


@pytest.mark.parametrize(
    "shv,obj",
    (
        ({}, RpcLogin("")),
        (
            {"login": {"password": "", "user": "admin", "type": "PLAIN"}},
            RpcLogin("admin"),
        ),
        (
            {
                "login": {
                    "password": "a7162d463b28666737f63034db39f03bca59b060",
                    "user": "admin",
                    "type": "SHA1",
                },
                "options": {
                    "device": {"mountPoint": "test/this"},
                    "other": 42,
                },
            },
            RpcLogin(
                "admin",
                "a7162d463b28666737f63034db39f03bca59b060",
                RpcLoginType.SHA1,
                {
                    "device": {"mountPoint": "test/this"},
                    "other": 42,
                },
            ),
        ),
    ),
)
def test_from_shv(shv, obj):
    assert RpcLogin.from_shv(shv) == obj


@pytest.mark.parametrize(
    "shv,msg",
    (([], "Expected Map."),),
)
def test_from_shv_invalid(shv, msg):
    with pytest.raises(RpcInvalidParamError, match=re.escape(msg)):
        RpcLogin.from_shv(shv)
