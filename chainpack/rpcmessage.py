from .rpcvalue import RpcValue
from .cpon import CponWriter
from .chainpack import ChainPackWriter


class RpcMessage:
    def __init__(self, rpc_val=None):
        if rpc_val is None:
            self.rpcValue = RpcValue()
        elif isinstance(rpc_val, RpcValue):
            self.rpcValue = rpc_val
        else:
            raise TypeError("RpcMessage cannot be constructed with: " + type(rpc_val))

        if self.rpcValue:
            if not self.rpcValue.meta:
                self.rpcValue.meta = {}
            if not self.rpcValue.value:
                self.rpcValue.value = {}
            self.rpcValue.type = RpcValue.Type.IMap

    TagRequestId = 8
    TagShvPath = 9
    TagMethod = 10
    TagCallerIds = 11

    KeyParams = 1
    KeyResult = 2
    KeyError = 3

    def is_valid(self):
        return True if isinstance(self.rpcValue, RpcValue) else False

    def is_request(self):
        return self.request_id() and self.method()

    def is_response(self):
        return self.request_id() and not self.method()

    def is_signal(self):
        return not self.request_id() and self.method()

    def make_response(self):
        if not self.is_request():
            raise ValueError("Response can be created from request only.")
        resp = RpcMessage()
        resp.set_request_id(self.request_id())
        resp.set_caller_ids(self.caller_ids())
        return resp

    def request_id(self):
        return self.rpcValue.meta.get(RpcMessage.TagRequestId) if self.is_valid() else None

    def set_request_id(self, rqid):
        self.rpcValue.meta[RpcMessage.TagRequestId] = rqid

    def shv_path(self):
        return self.rpcValue.meta.get(RpcMessage.TagShvPath) if self.is_valid() else None

    def set_shv_path(self, val):
        if val is None:
            self.rpcValue.meta.pop(RpcMessage.TagShvPath, None)
        else:
            self.rpcValue.meta[RpcMessage.TagShvPath] = val

    def caller_ids(self):
        return self.rpcValue.meta.get(RpcMessage.TagCallerIds) if self.is_valid() else None

    def set_caller_ids(self, val):
        if val is None:
            self.rpcValue.meta.pop(RpcMessage.TagCallerIds, None)
        else:
            self.rpcValue.meta[RpcMessage.TagCallerIds] = val

    def method(self):
        return self.rpcValue.meta.get(RpcMessage.TagMethod) if self.is_valid() else None

    def set_method(self, val):
        if val is None:
            self.rpcValue.meta.pop(RpcMessage.TagMethod, None)
        else:
            self.rpcValue.meta[RpcMessage.TagMethod] = val

    def params(self):
        return self.rpcValue.value.get(RpcMessage.KeyParams) if self.is_valid() else None

    def set_params(self, params):
        if params is None:
            self.rpcValue.value.pop(RpcMessage.KeyParams, None)
        else:
            self.rpcValue.value[RpcMessage.KeyParams] = params

    def result(self):
        return self.rpcValue.value.get(RpcMessage.KeyResult) if self.is_valid() else None

    def set_result(self, result):
        if result is None:
            self.rpcValue.value.pop(RpcMessage.KeyResult, None)
        else:
            self.rpcValue.value[RpcMessage.KeyResult] = result

    def error(self):
        return self.rpcValue.value.get(RpcMessage.KeyError) if self.is_valid() else None

    def set_error(self, err):
        if err is None:
            self.rpcValue.value.pop(RpcMessage.KeyError, None)
        else:
            self.rpcValue.value[RpcMessage.KeyError] = err

    def to_string(self):
        return CponWriter.pack(self.rpcValue).decode() if self.is_valid() else ''

    def to_cpon(self):
        return CponWriter.pack(self.rpcValue) if self.is_valid() else b''

    def to_chainpack(self):
        return ChainPackWriter.pack(self.rpcValue) if self.is_valid() else b''
