"""The base for the other RPC Types."""

from __future__ import annotations

import abc

from .. import SHVType


class RpcType(abc.ABC):
    """The base for the RPC Type specifications."""

    @abc.abstractmethod
    def validate(self, value: SHVType) -> bool:
        """Check if given value is of this type."""
