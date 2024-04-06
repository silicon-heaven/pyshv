"""SHV RPC Client that collects and provides history."""

import collections.abc
import dataclasses
import logging
import typing

from .. import RpcClient, RpcLogin, SimpleClient
from .base import RpcHistoryBase
from .log import RpcLog

logger = logging.getLogger(__name__)


class RpcHistoryClient(SimpleClient, RpcHistoryBase):
    """SHV RPC client that connects to server and mounts itself to .history."""

    APP_NAME: str = "pyshvhistory"
    """Name reported as application name for pyshvhistory."""

    def __init__(
        self,
        client: RpcClient,
        login: RpcLogin,
        logs: collections.abc.Sequence[RpcLog],
        *args: typing.Any,  # noqa AN204
        **kwargs: typing.Any,  # noqa AN204
    ) -> None:
        login = dataclasses.replace(
            login, options={"device": {"mountPoint": ".history"}}
        )
        super().__init__(client, login, logs, *args, **kwargs)
