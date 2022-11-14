import logging
import asyncio

from chainpack.rpcclient import RpcClient

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s[%(module)s:%(lineno)d] %(message)s')

async def test():
	client = RpcClient()
	print("connecting to broker")
	await client.connect(host='localhost', password='test', user='test', login_type=RpcClient.LoginType.Plain)
	print("connected OK")
	print("calling shv method 'echo'")
	await client.call_shv_method('.broker/app', 'echo', 42)
	resp = await client.read_rpc_message()
	print("response received:", resp.to_string())


if __name__ == "__main__":
	loop = asyncio.get_event_loop()
	loop.run_until_complete(test())
