"""The SHV RPC type oneof."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVType
from .base import RpcType
from .null import rpctype_null


class RpcTypeOneOf(RpcType):
    """The type that provides validation based on the multiple other types.

    If at least one of the provided types validates value then this type is
    valid.
    """

    def __init__(self, *args: RpcType) -> None:
        self._types = tuple(self.__inititer(args))

    @classmethod
    def __inititer(
        cls, types: collections.abc.Iterable[RpcType]
    ) -> collections.abc.Iterator[RpcType]:
        for tp in types:
            if isinstance(tp, RpcTypeOneOf):
                yield from cls.__inititer(tp.types)
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

    def validate(self, value: SHVType) -> typing.TypeGuard[float]:  # noqa: D102
        return any(t.validate(value) for t in self._types)


class RpcTypeOptional(RpcTypeOneOf):
    """The variant of :py:class:`RpcTypeOneOf` that implicitly adds :data:`rpctype_null`."""

    def __init__(self, *args: RpcType) -> None:
        if rpctype_null not in args:
            super().__init__(*args, rpctype_null)
        else:
            super().__init__(*args)
