"""Abstract definition of the broker configuration."""

from __future__ import annotations

import abc
import collections
import collections.abc

from ..rpcaccess import RpcAccess
from ..rpclogin import RpcLogin
from ..rpcurl import RpcUrl


class RpcBrokerRoleABC(abc.ABC):
    """Role used to control the peer's access and setup."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the role used to identify it externally."""

    def mount_point(  # noqa PLR6301
        self, existing: collections.abc.Set[str] = frozenset()
    ) -> str | None:
        """Provide mount point for this role.

        Note that root node, ``.app``, and ``.broker`` are never allowed to
        be mounted and thus should bever be returned.

        :param existing: Set of all existing mount points. They are provided
          to avoid these when mount points are being generated.
        :return: Iterator that generates possible mount points. Iterator that
          provides no item or just one is most common but generated mount points
          can be used as well.
        """
        return None

    def initial_subscriptions(self) -> collections.abc.Iterator[str]:  # noqa PLR6301
        """Iterate over subscription the peer should be initialized with.

        These subscription should be inserted as the initial set of
        subscriptions (TTL won't be applied on them).

        :return: Iterator over RPC RI for subscriptions.
        """
        return iter([])

    def access_level(self, path: str, method: str) -> RpcAccess | None:  # noqa PLR6301
        """Deduce the access level (if any) for given method.

        Note that all users have implicit browse access to the root node,
        ``.app``, ``.broker``, and ``.broker/currentClient`` that doesn't
        have to be covered by this function.

        :param path: SHV Path of the method.
        :param method: SHV Method name.
        :return: Access level for this method or ``None`` in case of no access.
        """
        return None


class RpcBrokerConfigABC(abc.ABC):
    """Abstract base for the SHV Broker configuration."""

    @property
    def name(self) -> str:
        """Name of the broker used to identify broker in UserID.

        The default is empty string and in such case broker name is not
        considered.
        """
        return ""

    def listens(self) -> collections.abc.Iterator[RpcUrl]:  # noqa PLR6301
        """Iterate over URLs where Broker should listen to."""
        return iter([])

    def connections(self) -> collections.abc.Iterator[tuple[RpcUrl, RpcBrokerRoleABC]]:  # noqa PLR6301
        """Iterate over URLs and their setup where Broker should connect to."""
        return iter([])

    @abc.abstractmethod
    def login(self, login: RpcLogin, nonce: str) -> RpcBrokerRoleABC | None:
        """Check the login and provide role if login is correct."""
