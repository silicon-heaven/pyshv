from __future__ import annotations

import collections.abc
import datetime
import typing
from enum import Enum


class RpcValue:
    class Type(Enum):
        Undefined = 0
        Null = 1
        Bool = 2
        Int = 3
        UInt = 4
        Double = 5
        Decimal = 6
        Blob = 7
        String = 8
        DateTime = 9
        List = 10
        Map = 11
        IMap = 12

    class DateTime:
        def __init__(self, msec, utc_offset):
            self.epochMsec = msec
            self.utcOffsetMin = utc_offset

        @classmethod
        def from_datetime(cls, dtime: datetime.datetime) -> RpcValue.DateTime:
            utcoff = dtime.utcoffset()
            return cls(
                int(dtime.timestamp() * 1000),
                -(utcoff.total_seconds() if utcoff is not None else 0),
            )

    class Decimal:
        def __init__(self, mantisa, exponent):
            self.mantisa = mantisa
            self.exponent = exponent

    pyreprT = typing.Union[
        None,
        bool,
        int,
        float,
        bytes,
        str,
        datetime.datetime,
        list,
        dict[typing.Union[str, int], "pyreprT"],
    ]
    pyreprMapT = typing.Optional[dict[typing.Union[str, int], pyreprT]]

    def __init__(
        self,
        value: pyreprT = None,
        meta: pyreprMapT = None,
        value_type: Type = Type.Undefined,
    ):
        self.set(value, meta, value_type)

    @property
    def type(self):
        return self._type

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value: typing.Any):
        self.set(value)

    @property
    def meta(self):
        return self._meta

    def set(
        self,
        value: pyreprT = None,
        meta: pyreprMapT = None,
        value_type: Type = Type.Undefined,
    ):
        self._meta = meta
        self._type = value_type
        if self._type is self.Type.Undefined:
            typemap: dict[typing.Type, RpcValue.Type] = {
                type(None): self.Type.Null,
                bool: self.Type.Bool,
                str: self.Type.String,
                int: self.Type.Int,
                bytes: self.Type.Blob,
                bytearray: self.Type.Blob,
                datetime.datetime: self.Type.DateTime,
                float: self.Type.Double,
                collections.abc.Sequence: self.Type.List,
            }
            for pytp, shvtp in typemap.items():
                if isinstance(value, pytp):
                    self._type = shvtp
                    break
            if isinstance(value, collections.abc.Mapping):
                self._type = (
                    self.Type.IMap
                    if all(isinstance(key, int) for key in value)
                    else self.Type.Map
                )

        self._value: typing.Union[
            None,
            bool,
            int,
            float,
            RpcValue.Decimal,
            bytes,
            str,
            RpcValue.DateTime,
            list[RpcValue],
            dict[str, RpcValue],
            dict[int, RpcValue],
        ]
        if self._type == self.Type.Null:
            self._value = None
        elif self._type == self.Type.Bool:
            self._value = bool(value)
        elif self._type == self.Type.Int:
            if not isinstance(value, int):
                raise TypeError(f"Invalid value for type Int: {repr(value)}")
            self._value = int(value)
        elif self._type == self.Type.UInt:
            if not isinstance(value, int) or value < 0:
                raise TypeError(f"Invalid value for type UInt: {repr(value)}")
            self._value = int(value)
        elif self._type == self.Type.Double:
            if not isinstance(value, float):
                raise TypeError(f"Invalid value for type Float: {repr(value)}")
            self._value = float(value)
        elif self._type == self.Type.Decimal:
            if not isinstance(value, (int, self.Decimal)):
                raise TypeError(f"Invalid value for type Decimal: {repr(value)}")
            self._value = (
                value
                if isinstance(value, self.Decimal)
                else self.Decimal(int(value), 0)
            )
        elif self._type == self.Type.Blob:
            if not isinstance(value, (bytes, bytearray)):
                raise TypeError(f"Invalid value for type Blob: {repr(value)}")
            self._value = bytes(value)
        elif self._type == self.Type.String:
            self._value = str(value)
        elif self._type == self.Type.DateTime:
            if not isinstance(value, (self.DateTime, datetime.datetime)):
                raise TypeError("DateTime as to be initialized from datetime.datetime")
            self._value = (
                value
                if isinstance(value, self.DateTime)
                else self.DateTime.from_datetime(value)
            )
        elif self._type == self.Type.List:
            assert isinstance(value, collections.abc.Sequence)
            self._value = [
                val if isinstance(val, RpcValue) else RpcValue(val) for val in value
            ]
        elif self._type == self.Type.Map:
            assert isinstance(value, collections.abc.Mapping)
            # TODO this can be modified trough value property!
            self._value = {
                str(key): val if isinstance(val, RpcValue) else RpcValue(val)
                for key, val in value.items()
            }
        elif self._type == self.Type.IMap:
            assert isinstance(value, collections.abc.Mapping)
            # TODO this can be modified trough value property!
            self._value = {
                int(key): val if isinstance(val, RpcValue) else RpcValue(val)
                for key, val in value.items()
            }
        else:
            raise TypeError(f"Unsupported value type: {self._type}: {repr(value)}")

    def is_valid(self):
        return self._type != self.Type.Undefined

    def to_str(self):
        if self._type == self.Type.String:
            return self._value
        if self._type == self.Type.Blob:
            return self._value.decode("utf-8")
        return str(self._value)

    def to_pyrepr(self) -> pyreprT:
        """Covert type recursivelly to their python representations."""
        if self._type == self.Type.Decimal:
            assert isinstance(self._value, self.Decimal)
            return self._value.mantisa * pow(10, self._value.exponent)
        if self._type == self.Type.List:
            assert isinstance(self._value, list)
            return [val.to_pyrepr() for val in self._value]
        if self._type in (self.Type.Map, self.Type.IMap):
            assert isinstance(self._value, dict)
            return {key: val.to_pyrepr() for key, val in self._value.items()}
        assert not isinstance(self._value, (self.Decimal, self.DateTime, list, dict))
        return self._value
