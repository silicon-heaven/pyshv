"""Configuration of the broker."""
import configparser
import dataclasses
import hashlib
import typing

from ..rpcmethod import RpcMethodAccess
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
        login_type: RpcLoginType = RpcLoginType.SHA1
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
                return self.password == password
            if login_type is RpcLoginType.SHA1:
                m = hashlib.sha1()
                m.update(nonce.encode("utf-8"))
                m.update(self.shapass.encode("utf-8"))
                return m.hexdigest() == password
            return False  # type: ignore

    def __init__(self) -> None:
        self.listen: dict[str, RpcUrl] = {}
        """URLs the broker should listen on."""
        self._users: dict[str, "RpcBrokerConfig.User"] = {}
        self._roles: dict[str, "RpcBrokerConfig.Role"] = {}

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

    def users(self) -> typing.Iterator[User]:
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

    def roles(self) -> typing.Iterator[Role]:
        """Iterate over all roles."""
        yield from self._roles.values()

    def login(
        self, user: str, password: str, nonce: str, login_type: RpcLoginType
    ) -> typing.Optional["RpcBrokerConfig.User"]:
        """Check the login and provide user if login is correct."""
        if user not in self._users or not self._users[user].validate_password(
            password, nonce, login_type
        ):
            return None
        return self.user(user)

    @classmethod
    def load(cls, config: configparser.ConfigParser) -> "RpcBrokerConfig":
        """Load configuration from ConfigParser."""
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
            if "password" in sec:
                password = sec["password"]
                login_type = RpcLoginType.PLAIN
            else:
                password = sec.get("sha1pass", "")
                login_type = RpcLoginType.SHA1
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
        return res
