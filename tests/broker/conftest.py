import pathlib

import pytest

from shv import broker


@pytest.fixture(name="config", scope="module")
def fixture_config():
    return broker.RpcBrokerConfig.load(pathlib.Path(__file__).parent / "config.toml")


@pytest.fixture(name="subconfig", scope="module")
def fixture_subconfig():
    return broker.RpcBrokerConfig.load(pathlib.Path(__file__).parent / "subconfig.toml")


@pytest.fixture(name="shvbroker")
async def fixture_shvbroker(config, url):
    config.listen = {"test": url}
    b = broker.RpcBroker(config)
    await b.start_serving()
    yield b
    await b.terminate()
