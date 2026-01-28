"""The SHV RPC type oneof."""

from __future__ import annotations

import collections.abc

from .. import SHVType
from .base import RpcType
from .null import rpctype_null


class RpcTypeOneOf(RpcType):
    """The type that provides validation based on the multiple other types.

    If at least one of the provided types validates value then this type is
    valid.
    """

    def __init__(self, *args: RpcType) -> None:
        self._types = tuple(self.__init_uniq_iter(args))

    @classmethod
    def __init_uniq_iter(
        cls, types: collections.abc.Iterable[RpcType]
    ) -> collections.abc.Iterator[RpcType]:
        yielded = []
        for tp in cls.__init_iter(types):
            if tp not in yielded:
                yield tp
                yielded.append(tp)

    @classmethod
    def __init_iter(
        cls, types: collections.abc.Iterable[RpcType]
    ) -> collections.abc.Iterator[RpcType]:
        for tp in types:
            if isinstance(tp, RpcTypeOneOf):
                yield from cls.__init_iter(tp.types)
            else:
                yield tp

    @property
    def types(self) -> tuple[RpcType, ...]:
        """Types this 'one of' allows."""
        return self._types

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeOneOf) and self._types == other._types

    def __str__(self) -> str:
        return "|".join(str(t) for t in self._types)

    def validate(self, value: SHVType) -> str | None:  # noqa: D102
        msgs = []
        for tp in self._types:
            if (msg := tp.validate(value)) is not None:
                msgs.append(msg)
            else:
                return None
        return " | ".join(msgs)


class RpcTypeOptional(RpcTypeOneOf):
    """The variant of :py:class:`RpcTypeOneOf` that implicitly adds :data:`rpctype_null`."""

    def __init__(self, *args: RpcType) -> None:
        super().__init__(*args, rpctype_null)
