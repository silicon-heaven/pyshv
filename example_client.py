#!/usr/bin/env python3
import argparse
import asyncio
import logging

from shv import RpcUrl, SimpleClient

log_levels = (
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
)


async def example_client(url: RpcUrl) -> None:
    client = await SimpleClient.connect(url)
    assert client is not None
    res = await client.call(".broker/app", "echo", 42)
    print(f"response received: {repr(res)}")
    await client.disconnect()


def parse_args() -> argparse.Namespace:
    """Parse passed arguments and return result."""
    parser = argparse.ArgumentParser(description="Silicon Heaven example client")
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
        "URL",
        nargs="?",
        default="tcp://test@localhost?password=test",
        help="SHV RPC URL specifying connection to the broker.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(
        level=log_levels[sorted([1 - args.v + args.q, 0, len(log_levels) - 1])[1]],
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
    )
    asyncio.run(example_client(RpcUrl.parse(args.URL)))
