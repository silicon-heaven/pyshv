class UnpackContext:
    class BufferUnderflow(Exception):
        pass

    def __init__(self, data):
        # assert isinstance(data, bytes)
        self.data = data
        self.index = 0

    def get_byte(self):
        if self.index >= len(self.data):
            raise UnpackContext.BufferUnderflow()
        ret = self.data[self.index]
        self.index += 1
        return ret

    def peek_byte(self):
        if self.index >= len(self.data):
            return -1
        return self.data[self.index]

    def get_bytes(self, literal):
        for c in literal:
            if c != self.get_byte():
                raise IndexError("'" + literal.decode() + "'' expected")


class PackContext:

    CHUNK_LEN = 1024

    def __init__(self):
        self.data = bytearray()
        self.length = 0

    def put_byte(self, b):
        if self.length >= len(self.data):
            new_len = len(self.data) + PackContext.CHUNK_LEN
            new_data = bytearray(new_len)
            new_data[0 : self.length] = self.data[0 : self.length]
            self.data = new_data
        self.data[self.length] = b
        self.length += 1

    def write_bytes(self, data):
        for b in data:
            self.put_byte(b)

    def write_utf8_string(self, text: str):
        self.write_bytes(text.encode())

    def data_bytes(self) -> bytes:
        return bytes(self.data[0 : self.length])
