#!/usr/bin/env python3
import asyncio
import logging

from shv import SimpleClient


async def test(port=3755):
    client = await SimpleClient.connect(
        host="localhost",
        port=port,
        user="test",
        password="test",
        login_type=SimpleClient.LoginType.PLAIN,
    )
    res = await client.call(".broker/app", "echo", 42)
    print(f"response received: {repr(res)}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG, format="%(levelname)s[%(module)s:%(lineno)d] %(message)s"
    )
    asyncio.run(test())
