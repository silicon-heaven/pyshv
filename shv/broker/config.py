"""Configuration of the broker."""

from __future__ import annotations

import collections.abc
import dataclasses
import hashlib
import pathlib
import tomllib

from ..rpcmethod import RpcMethodAccess
from ..rpcri import RpcRI
from ..rpcurl import RpcLoginType, RpcUrl


class RpcBrokerConfig:
    """SHV RPC Broker configuration."""

    @dataclasses.dataclass(frozen=True)
    class Role:
        """Generic roles assigned to the users."""

        name: str
        """Name of the role."""
        access: RpcMethodAccess = RpcMethodAccess.BROWSE
        """Access level granted to the user by this role."""
        match: frozenset[RpcRI] = dataclasses.field(default_factory=frozenset)
        """Reasource identifications this role applies on."""

        def method_applies(self, path: str, method: str) -> bool:
            """Check if this role applies on this method."""
            return any(ri.method_match(path, method) for ri in self.match)

        def signal_applies(self, path: str, source: str, signal: str) -> bool:
            """Check if this role applies on this signal."""
            return any(ri.signal_match(path, source, signal) for ri in self.match)

    @dataclasses.dataclass(frozen=True)
    class User:
        """User's login information."""

        name: str
        """Name of the user."""
        password: str
        """Password user needs to use to login."""
        login_type: RpcLoginType | None = RpcLoginType.SHA1
        """The password format (the default is SHA1). Use ``None`` to disable
        this user for login."""
        roles: collections.abc.Sequence[RpcBrokerConfig.Role] = dataclasses.field(
            default_factory=tuple
        )
        """Sequence of roles the user has assigned to."""

        def access_level(self, path: str, method: str) -> RpcMethodAccess | None:
            """Deduce access level (if any) for this user on given path and method."""
            for role in self.roles:
                if role.method_applies(path, method):
                    return role.access
            # These are defined paths we need to allow all users to access
            if path == ".broker/currentClient":
                return RpcMethodAccess.READ
            if path in {".app", ".broker"}:
                return RpcMethodAccess.BROWSE
            return None

        def access_level_signal(
            self, path: str, source: str, signal: str
        ) -> RpcMethodAccess | None:
            """Deduce access level (if any) for this user on given path, source and signal."""
            for role in self.roles:
                if role.signal_applies(path, source, signal):
                    return role.access
            return None

        def could_receive_signal(self, rid: RpcRI, path: str = "") -> bool:  # noqa PLR6301
            """Check if this user could even receive signal based on this subscription.

            This is used to optimize subscriptions for sub-brokers. There is no
            need to propagate subscription if it couldn't be received by the
            user anyway.

            Real access level of the signals is known only when received and
            thus this only checks if there is at least browse access level.

            The regular check when signal is actually received can be done with
            :meth:`access_level` as for any other message.

            :param ri: The RPC RI user subscribed for.
            :param path: Path to limit the subscription application.
            :return: ``True`` if signal might be deliverable to this user and
              ``False`` if user just doesn't have rights to get any such signal.
            """
            return True  # TODO

        @property
        def shapass(self) -> str:
            """Password in SHA1 format."""
            if self.login_type is RpcLoginType.SHA1:
                return self.password
            m = hashlib.sha1()  # noqa S324
            m.update(self.password.encode("utf-8"))
            return m.hexdigest()

        def validate_password(
            self,
            password: str,
            nonce: str,
            login_type: RpcLoginType = RpcLoginType.SHA1,
        ) -> bool:
            """Check if given password is correct."""
            if login_type is RpcLoginType.PLAIN:
                if self.login_type is RpcLoginType.PLAIN:
                    return self.password == password
                if self.login_type is RpcLoginType.SHA1:
                    hpass = hashlib.sha1(password.encode("utf-8")).hexdigest()  # noqa PLR6301
                    return self.shapass == hpass
            if login_type is RpcLoginType.SHA1:
                m = hashlib.sha1()  # noqa PLR6301
                m.update(nonce.encode("utf-8"))
                m.update(self.shapass.encode("utf-8"))
                return m.hexdigest() == password
            return False

    @dataclasses.dataclass(frozen=True)
    class Connection:
        """Connection to some other RPC broker."""

        name: str
        url: RpcUrl
        user: RpcBrokerConfig.User

    def __init__(self) -> None:
        self.listen: dict[str, RpcUrl] = {}
        """URLs the broker should listen on."""
        self.name: str = ""
        """Name of the broker used to identify broker in UserID."""
        self._connect: dict[str, RpcBrokerConfig.Connection] = {}
        self._users: dict[str, RpcBrokerConfig.User] = {}
        self._roles: dict[str, RpcBrokerConfig.Role] = {}

    def add_connection(self, connection: Connection) -> None:
        """Add or replace connection.

        :param connection: Connection definition.
        :raise ValueError: in case it specifies unknown user.
        """
        if connection.user is not self._users.get(connection.user.name, None):
            raise ValueError(f"Invalid user: '{connection.user.name}'")
        self._connect[connection.name] = connection

    def connection(self, name: str) -> Connection:
        """Get connection for given name.

        :param name: Name of the connection.
        :raise KeyError: when there is no such connection.
        """
        return self._connect[name]

    def connections(self) -> collections.abc.Iterator[Connection]:
        """Iterate over all connections."""
        yield from self._connect.values()

    def add_user(self, info: User) -> None:
        """Add or replace user.

        :param info: User description.
        :raise ValueError: in case it specifies unknown role.
        """
        for role in info.roles:
            if role is not self._roles.get(role.name, None):
                raise ValueError(f"Invalid role '{role.name}'")
        self._users[info.name] = info

    def user(self, name: str) -> User:
        """Get user for given name.

        :param name: Name of the user.
        :raise KeyError: when there is no such user.
        """
        return self._users[name]

    def users(self) -> collections.abc.Iterator[User]:
        """Iterate over all users."""
        yield from self._users.values()

    def add_role(self, role: Role) -> None:
        """Add or replace role.

        :param info: role description.
        :raise ValueError: in case it specifies unknown rule.
        """
        oldrole = self._roles.get(role.name, None)
        if oldrole is not None:
            for name, user in self._users.items():
                if oldrole in user.roles:
                    self._users[name] = dataclasses.replace(
                        user,
                        roles=tuple(role if r is oldrole else r for r in user.roles),
                    )
        self._roles[role.name] = role

    def role(self, name: str) -> Role:
        """Get role with given name.

        :param name: Name of the role.
        :raise KeyError: when there is no such role.
        """
        return self._roles[name]

    def roles(self) -> collections.abc.Iterator[Role]:
        """Iterate over all roles."""
        yield from self._roles.values()

    def login(
        self, user: str, password: str, nonce: str, login_type: RpcLoginType
    ) -> RpcBrokerConfig.User | None:
        """Check the login and provide user if login is correct."""
        try:
            u = self.user(user)
        except KeyError:
            pass
        else:
            if u.validate_password(password, nonce, login_type):
                return u
        return None

    @classmethod
    def load(cls, file: pathlib.Path) -> RpcBrokerConfig:
        """Load configuration from ConfigParser.

        :param config: Configuration to be loaded.
        :return: Broker configuration instance.
        :raise ValueError: When there is an issue in the configuration.
        :raise KeyError: When referencing non-existent user or role.
        """
        with file.open("rb") as f:
            data = tomllib.load(f)
        res = cls()
        res.name = str(data.pop("name", res.name))
        if listen := data.pop("listen", {}):
            if not isinstance(listen, collections.abc.Mapping):
                raise ConfigurationError("'listen' must be table of name and RPC URL")
            for name, url in listen.items():
                res.listen[name] = RpcUrl.parse(url)
        if roles := data.pop("roles", {}):
            if not isinstance(roles, collections.abc.Mapping):
                raise ConfigurationError("'roles' must be table")
            for name, role in roles.items():
                access = RpcMethodAccess.fromstr(role.pop("access", ""))
                rmatch = role.pop("match", [])
                if not isinstance(rmatch, collections.abc.Sequence):
                    raise ConfigurationError(f"'role.{name}.match' must be array")
                match = frozenset(RpcRI.parse(str(m)) for m in rmatch)
                res.add_role(cls.Role(name, access, match))
                if role:
                    raise ConfigurationError(
                        f"'roles.{name}' invalid table keys: {', '.join(role)}"
                    )
        if users := data.pop("users", {}):
            if not isinstance(users, collections.abc.Mapping):
                raise ConfigurationError("'users' must be table")
            for name, user in users.items():
                if "password" in user:
                    password = user.pop("password")
                    login_type = RpcLoginType.PLAIN
                elif "sha1pass" in user:
                    password = user.pop("sha1pass")
                    login_type = RpcLoginType.SHA1
                else:
                    password = ""
                    login_type = None
                rroles = user.pop("roles", [])
                if not isinstance(rroles, collections.abc.Sequence):
                    raise ConfigurationError(f"'users.{name}.roles' must be array")
                roles = tuple(res.role(m) for m in rroles)
                res.add_user(cls.User(name, password, login_type, roles))
                if user:
                    raise ConfigurationError(
                        f"'users.{name}' invalid table keys: {', '.join(user)}"
                    )
        if connect := data.pop("connect", {}):
            if not isinstance(connect, collections.abc.Mapping):
                raise ConfigurationError("'connect' must be table")
            for name, conn in connect.items():
                if not isinstance(conn, collections.abc.MutableMapping):
                    raise ConfigurationError(f"'connect.{name}' must be table")
                if "url" not in conn:
                    raise ConfigurationError(f"'connect.{name}.url' must be specified")
                if "user" not in conn:
                    raise ConfigurationError(f"'connect.{name}.user' must be specified")
                res.add_connection(
                    cls.Connection(
                        name,
                        RpcUrl.parse(conn.pop("url")),
                        res.user(str(conn.pop("user"))),
                    )
                )
                if conn:
                    raise ConfigurationError(
                        f"'connect.{name}' invalid table keys: {', '.join(conn)}"
                    )

        if data:
            raise ConfigurationError(f"Invalid table keys: {', '.join(data)}")
        return res


class ConfigurationError(ValueError):
    """The error in the configuration."""
