"""Abstraction of the SHV RPC device alert."""

import datetime
import enum
import typing

from .value import SHVIMapType, SHVType


class RpcAlert:
    """Device alert representation."""

    NOTICE_MIN: int = 0
    """The minimal value for the Notice level."""
    NOTICE_MAX: int = 20
    """The maximal value for the Notice level."""
    WARNING_MIN: int = 21
    """The minimal value for the Warning level."""
    WARNING_MAX: int = 42
    """The maximal value for the Warning level."""
    ERROR_MIN: int = 43
    """The minimal value for the Error level."""
    ERROR_MAX: int = 63
    """The maximal value for the Error level."""

    class Key(enum.IntEnum):
        """Key inm the alert IMap."""

        DATE = 0
        LEVEL = 1
        ID = 2
        INFO = 3

    def __init__(self, value: SHVIMapType | None = None) -> None:
        self.value: dict[int, SHVType] = dict(value) if value else {}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcAlert) and self.id == other.id

    @property
    def date(self) -> datetime.datetime:
        """Date and time of the alert creation."""
        value = self.value.get(self.Key.DATE)
        if not isinstance(value, datetime.datetime):
            raise ValueError(f"Must be datetime but is: {type(value)}")
        return value

    @date.setter
    def date(self, value: datetime.datetime) -> None:
        self.value[self.Key.DATE] = value

    @property
    def level(self) -> int:
        """Alert level."""
        value = self.value.get(self.Key.LEVEL)
        if not isinstance(value, int):
            raise ValueError(f"Must be int but is: {type(value)}")
        return value

    @level.setter
    def level(self, value: int) -> None:
        if value < self.NOTICE_MIN or value > self.ERROR_MAX:
            raise ValueError("Must be between 0 and 63")
        self.value[self.Key.LEVEL] = value

    @property
    def id(self) -> str:
        """Alert identifier."""
        value = self.value.get(self.Key.ID)
        if not isinstance(value, str):
            raise ValueError(f"Must be string but is: {type(value)}")
        return value

    @id.setter
    def id(self, value: str) -> None:
        self.value[self.Key.ID] = value

    @classmethod
    def new(
        cls, level: int, alert_id: str, date: datetime.datetime | None = None
    ) -> typing.Self:
        """Create a new alert."""
        return cls({
            cls.Key.DATE: date or datetime.datetime.now(),
            cls.Key.LEVEL: level,
            cls.Key.ID: alert_id,
        })
