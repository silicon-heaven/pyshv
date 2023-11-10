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


def parse_args() -> argparse.Namespace:
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


async def _broker_main(config: RpcBrokerConfig) -> None:
    broker = RpcBroker(config)
    try:
        await broker.serve_forever()
    finally:
        await broker.terminate()


def main() -> None:
    """Application's entrypoint."""
    args = parse_args()

    logging.basicConfig(
        level=log_levels[sorted([1 - args.v + args.q, 0, len(log_levels) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )

    config = configparser.ConfigParser()
    if args.config:
        config.read(args.config)
    brokerconf = RpcBrokerConfig.load(config)
    try:
        asyncio.run(_broker_main(brokerconf))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
