import asyncio

from chainpack.rpcclient import RpcClient
from chainpack.rpcclient import get_next_rpc_request_id
from chainpack.rpcmessage import RpcMessage
from chainpack.rpcvalue import RpcValue
from datetime import datetime


class ClientConnection:
    def __init__(self):
        self.connected = False
        self.receiverTask = None
        self.rpcClient = RpcClient()
        # shv_path_prefix -> handler
        self.signal_handlers = {}
        # request_id -> event
        self.response_events = {}
        # request_id -> RpcMessage
        self.response_messages = {}

    async def connect(self, host, port=3755, user=None, password=None,
                      login_type: RpcClient.LoginType = RpcClient.LoginType.Sha1):
        if not self.connected:
            await self.rpcClient.connect(host, port, user, password, login_type)
            self.connected = True
            self.receiverTask = asyncio.create_task(self.receiver_task())
        else:
            print("Can't connect, client already connected")

    async def disconnect(self):
        if self.connected and self.receiverTask is not None:
            self.receiverTask.cancel()
            self.connected = False

    async def call_shv_method_blocking(self, shv_path, method, params=None):
        if self.connected:
            req_id = get_next_rpc_request_id()
            response_event = asyncio.Event()
            self.response_events[req_id] = response_event
            await self.rpcClient.call_shv_method_with_id(req_id, shv_path, method, params)
            await response_event.wait()
            return self.response_messages.pop(req_id)
        else:
            raise Exception("Client not connected")

    def set_value_change_handler(self, shv_path: str, handler):
        shv_path = shv_path.encode()
        self.signal_handlers[shv_path] = handler
        # print(f"Setting signal handler for path: {shv_path}")

    async def subscribe_path(self, shv_path):
        resp = await self.call_shv_method_blocking('.broker/app', 'subscribe', shv_path)
        if not resp.result().value:
            self.signal_handlers.pop(shv_path)
            print(f"Subscription for {shv_path} failed: {resp.error()}")

    async def get_snapshot_and_update(self, shv_home: str):
        params = {"recordCountLimit": 10000,
                  "withPathsDict": True,
                  "withSnapshot": True,
                  "withTypeInfo": False,
                  "since": datetime.now()
                  }
        resp = await self.call_shv_method_blocking(shv_home, "getLog", params)
        result: RpcValue = resp.result()
        if result:
            result_metadata: dict = result.meta
            paths_dict: dict = result_metadata.get('pathsDict').value

            # for idx, path in paths_dict.items():
            #     print(f'idx: {idx} dict path: {path.value}')

            result_data: list = result.value
            for list_item in result_data:
                idx = list_item.value[1].value
                value = list_item.value[2].value
                path = paths_dict[idx].value
                # print(f'idx: {idx}, path: {path}, val: {value}')
                self.update_value_for_path(path, value)

    def update_value_for_path(self, path: bytes, value):
        prefix_handler = find_value_for_longest_prefix(path, self.signal_handlers)
        if prefix_handler is not None:
            prefix, handler = prefix_handler
            # print(f"Updating path: {path}, value: {value}")
            # asyncio.get_event_loop().call_soon(handler, new_path, value)
            handler(path, value)

    async def receiver_task(self):
        while True:
            msg = await self.rpcClient.read_rpc_message()
            if msg.is_response():
                req_id = msg.request_id().value
                # print(f"received resp, id: {req_id}")
                if req_id in self.response_events:
                    self.response_messages[req_id] = msg
                    event = self.response_events.pop(req_id)
                    event.set()
            elif msg.is_signal():
                method = msg.method().value
                path = msg.shv_path().value
                if method == b'chng':
                    prefix_handler = find_value_for_longest_prefix(path, self.signal_handlers)
                    if prefix_handler is not None:
                        prefix, handler = prefix_handler
                        # print(f"Calling chng signal handler for path {path}, prefix {prefix}")
                        asyncio.get_event_loop().call_soon(handler, path, msg.params().value)
                # else:
                #     print(f"Unhandled signal, path: {path}, method: {method}")


def find_value_for_longest_prefix(key: bytes, dictionary: dict):
    split_key = key.split(b'/')
    while len(split_key) > 0:
        if key in dictionary:
            return key, dictionary.get(key)
        split_key.pop()
        key = b'/'.join(split_key)
    return None

