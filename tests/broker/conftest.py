import configparser
import dataclasses
import pathlib

import pytest

from shv import RpcUrl, broker


@pytest.fixture(name="config", scope="module")
def fixture_config():
    config = configparser.ConfigParser()
    config.read(pathlib.Path(__file__).parent / "pyshvbroker.ini")
    return broker.RpcBrokerConfig.load(config)


@pytest.fixture(name="subconfig", scope="module")
def fixture_subconfig():
    config = configparser.ConfigParser()
    config.read(pathlib.Path(__file__).parent / "pyshvsubbroker.ini")
    return broker.RpcBrokerConfig.load(config)


@pytest.fixture(name="shvbroker")
async def fixture_shvbroker(config, url):
    config.listen = {"test": url}
    b = broker.RpcBroker(config)
    await b.start_serving()
    yield b
    await b.terminate()
