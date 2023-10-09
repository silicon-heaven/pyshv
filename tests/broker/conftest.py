import configparser
import pathlib

import pytest

from shv import broker


@pytest.fixture(name="parsed_config", scope="module")
def fixture_parsed_config():
    config = configparser.ConfigParser()
    config.read(pathlib.Path(__file__).parent / "pyshvbroker.ini")
    return config


@pytest.fixture(name="config")
def fixture_config(parsed_config):
    return broker.RpcBrokerConfig.load(parsed_config)


@pytest.fixture(name="shvbroker")
async def fixture_shvbroker(config, url):
    config.listen = {"test": url}
    b = broker.RpcBroker(config)
    await b.start_serving()
    yield b
    await b.terminate()
