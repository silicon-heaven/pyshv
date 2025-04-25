"""Check that errors can be created trough RpcError."""

import pytest

from shv import (
    RpcError,
    RpcInvalidParamError,
    RpcLoginRequiredError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
    RpcNotImplementedError,
    RpcRequestInvalidError,
    RpcTryAgainLaterError,
    RpcUserIDRequiredError,
)

errors = (
    RpcMethodNotFoundError,
    RpcInvalidParamError,
    RpcMethodCallExceptionError,
    RpcLoginRequiredError,
    RpcUserIDRequiredError,
    RpcNotImplementedError,
    RpcTryAgainLaterError,
    RpcRequestInvalidError,
)


@pytest.mark.parametrize("cls", (RpcError, *errors))
def test_new_error(cls):
    obj = RpcError("foo", cls.shv_error_code)
    assert isinstance(obj, cls)
    assert obj.error_code == cls.shv_error_code
    assert obj.message == "foo"


@pytest.mark.parametrize("cls", errors)
def test_new_direct_error(cls):
    obj = cls("foo")
    assert isinstance(obj, RpcError)
    assert obj.error_code == cls.shv_error_code
    assert obj.message == "foo"
