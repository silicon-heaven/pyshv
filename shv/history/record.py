"""The record in RPC History."""

from __future__ import annotations

import dataclasses
import datetime

from .. import RpcMessage, RpcMethodAccess, SHVType


@dataclasses.dataclass
class RpcHistoryRecord:
    """Record keeped by RPC History."""

    path: str
    """SHV RPC path."""
    signal: str
    """SHV RPC signal name."""
    source: str
    """SHV RPC method name signal is associated with."""
    data: SHVType
    """SHV RPC signal parameter."""
    user_id: str | None
    """User identifier of the record."""
    access: RpcMethodAccess
    """The access level of the recorded signal."""
    snapshot: bool
    """Record is repetition of record in the history, not change of the value.

    To reduce need to pass the whole database to get all possible records we
    instead repeat records once they are too far from the current latest record.
    To recognize that we use this flag to inform us about it being repetition.
    """
    time_monotonic: datetime.datetime
    """Monotonic time of the record creation."""
    time_device: datetime.datetime | None
    """Device's time of the record creation if time of the device skips back."""

    @classmethod
    def new(cls, msg: RpcMessage) -> RpcHistoryRecord:
        """Create new record."""
        assert msg.is_signal
        return cls(
            msg.path,
            msg.signal_name,
            msg.source,
            msg.param,
            msg.user_id,
            msg.rpc_access or RpcMethodAccess.READ,
            False,
            datetime.datetime.now().astimezone(),
            None,
        )
