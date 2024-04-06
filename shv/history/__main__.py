"""Implementation of generic SHV history collector and provider."""

import argparse
import asyncio
import configparser
import itertools
import logging

from .. import RpcSubscription, RpcUrl
from .client import RpcHistoryClient
from .database import RpcHistoryDB

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
    parser = argparse.ArgumentParser(
        "pyshvhistory", description="Silicon Heaven history collector and provider"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {RpcHistoryClient.APP_VERSION}",
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
        "--db",
        action="store",
        help="Path to database file used to store the history data.",
    )
    parser.add_argument(
        "-s",
        "--sub",
        action="append",
        default=[],
        help="Subscriptions used to collect history. The format is PATH:METHOD "
        + "or PATTERN::PATTERN_METHOD. ':chng' is used if no sub is specified.",
    )
    parser.add_argument(
        "--url",
        action="store",
        help="SHV RPC URL for connection to the broker. It is preferred to use "
        + "config for connection because this is visible to all users and can "
        + "contain password.",
    )
    parser.add_argument(
        "-c",
        "--config",
        action="store",
        default="/etc/pyshvhistory.ini",
        help="Configuration file",
    )
    return parser.parse_args()


async def _history_main(
    url: RpcUrl, db: RpcHistoryDB, subs: list[RpcSubscription]
) -> None:
    client = await RpcHistoryClient.connect(url, db)
    for sub in subs:
        await client.subscribe(sub)
    await client.task
    await client.disconnect()


def main() -> None:
    """Application's entrypoint."""
    args = parse_args()

    logging.basicConfig(
        level=log_levels[sorted([1 - args.v + args.q, 0, len(log_levels) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )

    config = configparser.ConfigParser()
    config.read(args.config)

    url = RpcUrl.parse(
        args.url or config.get("config", "url", fallback="tcp://localhost")
    )
    db = RpcHistoryDB(
        args.db or config.get("config", "dbpath", fallback="pyshvhistory.db"),
        cleanup=True,
    )
    return

    subs: list[RpcSubscription] = [
        RpcSubscription.fromStr(sub)
        for sub in itertools.chain(
            args.sub, config.get("config", "subscriptions", fallback="").split()
        )
        if sub
    ]
    if not subs:
        subs.append(RpcSubscription())

    try:
        asyncio.run(_history_main(url, db, subs))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
