import configparser
import pathlib
import sqlite3

import pytest

from shv.broker import RpcBroker, RpcBrokerConfig


@pytest.fixture(name="dbpath")
def fixture_dbpath(tmp_path):
    return tmp_path / "history.db"


@pytest.fixture(name="files_path")
def fixture_files_path(tmp_path):
    return tmp_path / "files"


@pytest.fixture(name="db")
def fixture_db(dbpath):
    return sqlite3.Connection(dbpath)


@pytest.fixture(name="shvbroker")
async def fixture_shvbroker(url):
    """Use our broker instead of C++ one."""
    rconfig = configparser.ConfigParser()
    rconfig.read(pathlib.Path(__file__).parent.parent / "broker/pyshvbroker.ini")
    config = RpcBrokerConfig.load(rconfig)
    config.listen = {"test": url}
    b = RpcBroker(config)
    await b.start_serving()
    yield b
    await b.terminate()
