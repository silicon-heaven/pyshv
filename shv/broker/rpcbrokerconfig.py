"""Configuration of the broker."""
from __future__ import annotations

import collections.abc
import configparser
import dataclasses
import hashlib
import typing

from ..rpcmethod import RpcMethodAccess
from ..rpcsubscription import RpcSubscription
from ..rpcurl import RpcLoginType, RpcUrl


class RpcBrokerConfig:
    """Generic store of broker configuration."""

    @dataclasses.dataclass(frozen=True)
    class Method:
        """Combination of method and SHV path."""

        path: str = ""
        """Path prefix that need to match for this to apply."""
        method: str = ""
        """Method name that should be matched. Empty matches all methods."""

        @classmethod
        def fromstr(cls, string: str) -> "RpcBrokerConfig.Method":
            """Parse :class:`RpcBrokerConfig.Method` from string."""
            if ":" not in string:
                raise ValueError(f"Invalid specification of method: {string}")
            return cls(*string.split(":", maxsplit=1))

        def applies(self, path: str, method: str) -> bool:
            """Check if this method applies to this combination of path and method."""
            return (
                not self.path or path == self.path or path.startswith(self.path + "/")
            ) and (not self.method or method == self.method)

    @dataclasses.dataclass(frozen=True)
    class Role:
        """Generic roles assigned to the users."""

        name: str
        """Name of the role."""
        access: RpcMethodAccess = RpcMethodAccess.BROWSE
        """Access level granted to the user by this role."""
        methods: frozenset["RpcBrokerConfig.Method"] = dataclasses.field(
            default_factory=frozenset
        )
        """Methods used to check if this role should apply."""
        roles: frozenset["RpcBrokerConfig.Role"] = dataclasses.field(
            default_factory=frozenset
        )
        """Additional roles to applied after this role."""

        def applies(self, path: str, method: str) -> bool:
            """Check if this role applies on any method."""
            return any(rule.applies(path, method) for rule in self.methods)

    @dataclasses.dataclass(frozen=True)
    class User:
        """User's login information."""

        name: str
        password: str
        login_type: RpcLoginType | None = RpcLoginType.SHA1
        roles: frozenset["RpcBrokerConfig.Role"] = dataclasses.field(
            default_factory=frozenset
        )

        def all_roles(self) -> typing.Iterator["RpcBrokerConfig.Role"]:
            """Iterate over all roles assigned to this user."""
            rlst = list(self.roles)
            while rlst:
                role = rlst.pop()
                yield role
                rlst.extend(role.roles)

        def access_level(self, path: str, method: str) -> RpcMethodAccess | None:
            """Deduce access level (if any) for this user on given path and method."""
            for role in self.all_roles():
                if role.applies(path, method):
                    return role.access
            # These are defined paths we need to allow all users to access
            if path == ".app/broker/currentClient":
                return RpcMethodAccess.READ
            if path in (".app", ".app/broker"):
                return RpcMethodAccess.BROWSE
            return None

        def could_receive_signal(
            self, subscription: RpcSubscription, path: str = ""
        ) -> bool:
            """Check if this user could even receive signal based on this subscription.

            This is used to optimize subscriptions for sub-brokers. There is no
            need to propagate subscription if it couldn't be received by the
            user anyway.

            Real access level of the signals is known only when received and
            thus this only checks if there is at least browse access level.

            The regular check when signal is actually received can be done with
            :meth:`access_level` as for any other message.

            :param subscription: The subscription to use for check.
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
            m = hashlib.sha1()
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
                    hpass = hashlib.sha1(password.encode("utf-8")).hexdigest()
                    return self.shapass == hpass
            if login_type is RpcLoginType.SHA1:
                m = hashlib.sha1()
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
        for srole in role.roles:
            if srole is not self._roles.get(srole.name, None):
                raise ValueError(f"Invalid role '{srole.name}'")
        oldrole = self._roles.get(role.name, None)
        if oldrole is not None:
            for name, srole in self._roles.items():
                if oldrole in srole.roles:
                    self._roles[name] = dataclasses.replace(
                        srole, roles=(srole.roles ^ {oldrole, role})
                    )
            for name, user in self._users.items():
                if oldrole in user.roles:
                    self._users[name] = dataclasses.replace(
                        user, roles=(user.roles ^ {oldrole, role})
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
    ) -> typing.Optional["RpcBrokerConfig.User"]:
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
    def load(cls, config: configparser.ConfigParser) -> "RpcBrokerConfig":
        """Load configuration from ConfigParser.

        :param config: Configuration to be loaded.
        :return: Broker configuration instance.
        :raise ValueError: When there is an issue in the configuration.
        :raise KeyError: When referencing non-existent user or role.
        """
        # TODO do not ignore uknown options and sections
        res = cls()
        if "listen" in config:
            for name, url in config["listen"].items():
                res.listen[name] = RpcUrl.parse(url)
        for secname, sec in filter(lambda v: v[0].startswith("roles."), config.items()):
            res.add_role(
                cls.Role(
                    secname[6:],
                    RpcMethodAccess.fromstr(sec.get("access", "")),
                    frozenset(
                        cls.Method.fromstr(method)
                        for method in sec.get("methods", "").split()
                    ),
                )
            )
        for secname, sec in filter(lambda v: v[0].startswith("roles."), config.items()):
            roles = sec.get("roles", "").split()
            name = secname[6:]
            if roles:
                res.add_role(
                    dataclasses.replace(
                        res.role(name),
                        roles=frozenset(map(res.role, roles)),
                    )
                )
        for secname, sec in filter(lambda v: v[0].startswith("users."), config.items()):
            login_type: RpcLoginType | None
            if "password" in sec:
                password = sec["password"]
                login_type = RpcLoginType.PLAIN
            elif "sha1pass" in sec:
                password = sec["sha1pass"]
                login_type = RpcLoginType.SHA1
            else:
                password = ""
                login_type = None
            res.add_user(
                cls.User(
                    secname[6:],
                    password,
                    login_type,
                    frozenset(
                        res.role(role_name)
                        for role_name in sec.get("roles", "").split()
                    ),
                )
            )
        for secname, sec in filter(
            lambda v: v[0].startswith("connect."), config.items()
        ):
            if "url" not in sec:
                raise ValueError(f"Connect requires 'url' option in {secname}")
            if "user" not in sec:
                raise ValueError(f"Connect requires 'user' option in {secname}")
            name = secname[8:]
            res.add_connection(
                cls.Connection(name, RpcUrl.parse(sec["url"]), res.user(sec["user"]))
            )

        return res
