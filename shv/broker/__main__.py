"""Implementation of generic SHV RPC broker."""

import argparse
import asyncio
import logging
import pathlib

from .broker import RpcBroker
from .config import RpcBrokerConfig

logger = logging.getLogger(__name__)


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
    levels = [level for level in logging.getLevelNamesMapping() if level != "NOTSET"]
    parser.add_argument(
        "--log-level",
        action="store",
        choices=levels,
        help="Set logging level exactly to specific level (ignores -v and -q)."
        + f"The default level is WARNING. Supported levels: {', '.join(levels)}",
    )
    parser.add_argument(
        "-c",
        "--config",
        action="store",
        default="/etc/pyshvbroker.toml",
        type=pathlib.Path,
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
        level=logging.getLevelNamesMapping()[args.log_level]
        if args.log_level
        else logging.WARN + ((args.q - args.v) * 10),
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )

    brokerconf = RpcBrokerConfig.load(args.config)
    try:
        asyncio.run(_broker_main(brokerconf))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
