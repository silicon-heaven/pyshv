"""Implementation of generic SHV RPC broker."""
import argparse
import asyncio
import configparser
import logging

from .rpcbroker import RpcBroker
from .rpcbrokerconfig import RpcBrokerConfig

logger = logging.getLogger(__name__)
log_levels = (
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
)


def parse_args():
    """Parse passed arguments and return result."""
    parser = argparse.ArgumentParser("pyshvbroker", description="Silicon Heaven broker")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {RpcBroker.Client.APP_VERSION}",
    )
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="Increase verbosity level of logging",
    )
    parser.add_argument(
        "-q",
        action="count",
        default=0,
        help="Decrease verbosity level of logging",
    )
    parser.add_argument(
        "-c",
        "--config",
        action="store",
        default="",
        help="Configuration file",
    )
    return parser.parse_args()


async def async_main() -> None:
    """Application's entrypoint coroutine."""
    args = parse_args()

    logging.basicConfig(
        level=log_levels[sorted([1 - args.v + args.q, 0, len(log_levels) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )

    config = configparser.ConfigParser()
    if args.config:
        config.read(args.config)
    brokerconf = RpcBrokerConfig.load(config)
    broker = RpcBroker(brokerconf)
    await broker.serve_forever()


def main() -> None:
    """Application's entrypoint."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
