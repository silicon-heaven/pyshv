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
    class Rule:
        """Description of access rule."""

        name: str
        """Name of the rule."""
        path: str = ""
        """Path prefix that need to match for this rule to apply."""
        methods: frozenset[str] = dataclasses.field(default_factory=frozenset)
        """Set of methods this rule matches. Empty set matches all methods."""

        def applies(self, path: str, method: str) -> bool:
            """Check if this rule applies."""
            return (not self.methods or method in self.methods) and path.startswith(
                self.path
            )

    @dataclasses.dataclass(frozen=True)
    class Role:
        """Generic roles assigned to the users."""

        name: str
        """Name of the role."""
        access: RpcMethodAccess = RpcMethodAccess.BROWSE
        """Access level granted to the user by this role."""
        rules: frozenset["RpcBrokerConfig.Rule"] = dataclasses.field(
            default_factory=frozenset
        )
        """Rules used to check if this role should apply."""
        roles: frozenset["RpcBrokerConfig.Role"] = dataclasses.field(
            default_factory=frozenset
        )
        """Additional roles to check."""

        def applies(self, path: str, method: str) -> bool:
            """Check if this role applies by this rules."""
            return any(rule.applies(path, method) for rule in self.rules)

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
            return False

    def __init__(self) -> None:
        self.listen: dict[str, RpcUrl] = {}
        """URLs the broker should listen on."""
        self._users: dict[str, "RpcBrokerConfig.User"] = {}
        self._roles: dict[str, "RpcBrokerConfig.Role"] = {}
        self._rules: dict[str, "RpcBrokerConfig.Rule"] = {}

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
        for rule in role.rules:
            if rule is not self._rules.get(rule.name, None):
                raise ValueError(f"Invalid rule '{rule.name}'")
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

    def add_rule(self, rule: Rule) -> None:
        """Add or replace rule.

        :param info: rule description.
        """
        oldrule = self._rules.get(rule.name, None)
        if oldrule is not None:
            for name, role in self._roles.items():
                if oldrule in role.rules:
                    self._roles[name] = dataclasses.replace(
                        role, rules=(role.rules ^ {oldrule, rule})
                    )
        self._rules[rule.name] = rule

    def rule(self, name: str) -> Rule:
        """Get rule with given name.

        :param name: Name of the rule.
        :raise KeyError: when there is no such rule.
        """
        return self._rules[name]

    def rules(self) -> typing.Iterator[Rule]:
        """Iterate over all rules."""
        yield from self._rules.values()

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
        for secname, sec in filter(lambda v: v[0].startswith("rules."), config.items()):
            res.add_rule(
                cls.Rule(
                    secname[6:],
                    sec.get("path", ""),
                    frozenset(sec.get("methods", "").split()),
                )
            )
        for secname, sec in filter(lambda v: v[0].startswith("roles."), config.items()):
            res.add_role(
                cls.Role(
                    secname[6:],
                    RpcMethodAccess.fromstr(sec.get("access", "")),
                    frozenset(
                        res.rule(rule_name)
                        for rule_name in sec.get("rules", "").split()
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
