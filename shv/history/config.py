"""SHV RPC History configuration."""

from __future__ import annotations

import configparser
import dataclasses

from .. import RpcUrl


class RpcHistoryConfig:
    """SHV RPC History configuration."""

    @dataclasses.dataclass
    class Log:
        """Single log to be recorded."""

    class RecordsLog(Log):
        """Log based on record database."""

    class FilesLog(Log):
        """Log based on files."""

    @dataclasses.dataclass
    class Pull:
        """The logs pulling configuration."""

    def __init__(self) -> None:
        self.url: RpcUrl = RpcUrl.parse("localhost")
        """URL the history should connect to."""

    @classmethod
    def load(cls, config: configparser.ConfigParser) -> RpcHistoryConfig:
        """Load configuration from ConfigParser.

        :param config: Configuration to be loaded.
        :return: History configuration instance.
        :raise ValueError: When there is an issue in the configuration.
        """
        res = cls()
        if "config" in config:
            res.url = RpcUrl.parse(config["config"].get("url", "localhost"))
        for secname, sec in filter(
            lambda v: v[0].startswith("records."), config.items()
        ):
            pass
        for secname, sec in filter(lambda v: v[0].startswith("files."), config.items()):
            pass
        for secname, sec in filter(lambda v: v[0].startswith("pull."), config.items()):
            pass

        return res
