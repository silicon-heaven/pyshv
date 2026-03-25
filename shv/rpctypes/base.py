"""The base for the other RPC Types."""

from __future__ import annotations

import abc

from .. import SHVType


class RpcType(abc.ABC):
    """The base for the RPC Type specifications."""

    def is_valid(self, value: SHVType, is_updatable: bool = False) -> bool:
        """Check if given value is of this type.

        :param value: The value to be validated.
        :oaram is_updatable: If :data:`shv.rpcdef.RpcDir.Flag.IS_UPDATABLE` was
          specified for this type. This is used only to validate argument for
          the method call that has this flag. Otherwise it should be ``False``.
        :return: ``True`` if value matches the type and ``False`` otherwise.
        """
        return self.validate(value, is_updatable) is None

    @abc.abstractmethod
    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:
        """Validate and possibly return error if invalid.

        :param value: Value to be validated.
        :oaram is_updatable: If :data:`shv.rpcdef.RpcDir.Flag.IS_UPDATABLE` was
          specified for this type. This is used only to validate argument for
          the method call that has this flag. Otherwise it should be ``False``.
        :return: ``None`` in case it is valid and string with English sentense
          explaining the validation error cause.
        """

    def inflate(self, value: SHVType) -> SHVType:
        """Convert some container types to Maps.

        This is advantegous if you want to get readable version of some more
        cryptic types (such as Struct or Bitfield).

        :param value: Value to be inflated.
        :return: Inflated value.
        :raise ValueError: In case passed value doesn't match the type.
        """
        if (msg := self.validate(value)) is not None:
            raise ValueError(msg)
        return value

    def deflate(self, value: SHVType) -> SHVType:
        """Convert Maps to some other container types.

        This is reverse operation of :meth:`inflate`.

        :param value: Value to be deflated.
        :return: Deflated value.
        :raise ValueError: In case passed value doesn't match the type.
        """
        if (msg := self.validate(value)) is not None:
            raise ValueError(msg)
        return value
