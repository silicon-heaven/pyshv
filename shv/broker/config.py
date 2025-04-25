"""Configuration of the broker."""

from __future__ import annotations

import collections.abc
import dataclasses
import fnmatch
import itertools
import logging
import pathlib
import tomllib
import typing

from ..rpcaccess import RpcAccess
from ..rpclogin import RpcLogin, RpcLoginType
from ..rpcri import rpcri_match
from ..rpcurl import RpcUrl
from .configabc import RpcBrokerConfigABC, RpcBrokerRoleABC
from .utils import nmax

logger = logging.getLogger(__name__)


class NamedProtocol(typing.Protocol):
    """The typing protocol for the objects with ``name`` property."""

    @property
    def name(self) -> str: ...  # noqa: D102


NamedT = typing.TypeVar("NamedT", bound=NamedProtocol)


class NamedMap(collections.abc.Mapping[str, NamedT]):
    """Helper to store and access objects that have name property."""

    def __init__(self, items: collections.abc.Iterable[NamedT] | None = None) -> None:
        self._items = {i.name: i for i in (items or [])}

    def __getitem__(self, name: str) -> NamedT:
        return self._items[name]

    def __iter__(self) -> collections.abc.Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NamedMap) and self._items == other._items

    def __repr__(self) -> str:
        return repr(list(self._items.values()))

    def add(self, item: NamedT) -> None:
        """Add a new item. This replaced old user with the same name."""
        self._items[item.name] = item

    def remove(self, user: RpcBrokerConfig.User | str) -> None:
        """Remove item."""
        del self._items[user if isinstance(user, str) else user.name]


@dataclasses.dataclass
class RpcBrokerConfig(RpcBrokerConfigABC):
    """Configuration for the SHV RPC Broker."""

    @dataclasses.dataclass
    class Role:
        """The configured role."""

        name: str
        """Name of this role."""
        mount_points: set[str] = dataclasses.field(default_factory=set)
        """Set of patterns for mount points allowed to this role."""
        access: dict[RpcAccess, set[str]] = dataclasses.field(default_factory=dict)
        """Resource identifiers used to assign highest possible access level."""

        def access_level(self, path: str, method: str) -> RpcAccess | None:
            """Deduce access level for method based on these rules."""
            for level in sorted(RpcAccess, reverse=True):
                if any(
                    rpcri_match(ri, path, method) for ri in self.access.get(level, [])
                ):
                    return level
            return None

    @dataclasses.dataclass
    class Autosetup:
        """Automatic setup based on device ID for this role."""

        device_id: set[str]
        """Set of patterns for device ID matching."""
        roles: set[str] = dataclasses.field(default_factory=set)
        """Set of roles that must match role assigned to the user."""
        mount_point: str | None = None
        """Mount point assigned by this autosetup.

        Mount point can contain `%` prefix stand-ins that are replaced when
        applied for the real mount point.

        * ``%d`` is replaced with device ID provided by client in login.
        * ``%r`` is replaced with role assigned to the user (multiple roles are
          joined with ``-``).
        * ``%u`` is replaced with user's name.
        * ``%i`` is a unique number. This is used in case mount point without it
          already exists. It starts on ``1`` and the first unused mount point is
          used while counting upward.
        * ``%I`` is a unique number from ``0`` that is increased until not yet
          used mount point is located.
        * ``%%`` is replaced with plain ``%``
        """
        subscriptions: set[str] = dataclasses.field(default_factory=set)
        """Set of initial subscriptions."""

        def generate_mount_point(
            self,
            existing: collections.abc.Set[str],
            device_id: str,
            user: RpcBrokerConfig.User,
        ) -> str | None:
            """Generate an appropriate mount point."""
            if self.mount_point:
                for i in itertools.count():
                    mp = self.mount_point
                    res = ""
                    constlen = None
                    while True:
                        r, sep, mp = mp.partition("%")
                        res += r
                        if sep == "%":
                            match mp[0]:
                                case "d":
                                    res += device_id
                                case "r":
                                    res += "-".join(user.roles)
                                case "u":
                                    res += user.name
                                case "i":
                                    if constlen is None:
                                        constlen = len(res)
                                    if i:
                                        res += str(i)
                                case "I":
                                    if constlen is None:
                                        constlen = len(res)
                                    res += str(i)
                                case "%":
                                    res += "%"
                                case char:
                                    res += "%" + char
                            mp = mp[1:]
                        else:
                            break

                    generate_new = False
                    for mnt in existing:
                        if mnt == res or res.startswith(mnt + "/"):
                            if constlen is None or len(mnt) < constlen:
                                return None  # Can't generate unique path
                            generate_new = True
                    if not generate_new:
                        return res
            return None

    @dataclasses.dataclass
    class User:
        """The user used to login to the broker."""

        name: str
        """Username of this user."""
        password: str
        """Password user needs to use to login."""
        roles: list[str] = dataclasses.field(default_factory=list)
        """Roles assigned to this user."""
        login_type: RpcLoginType = RpcLoginType.PLAIN
        """The password format (the default is SHA1)."""

        class Role(RpcBrokerRoleABC):
            """Broker role for logged in user."""

            def __init__(
                self,
                config: RpcBrokerConfig,
                user: RpcBrokerConfig.User,
                device_id: str | None = None,
                mount_point: str | None = None,
            ) -> None:
                self.config = config
                self.user = user
                self.device_id = device_id
                self._mount_point = mount_point

            @property
            def name(self) -> str:  # noqa D102
                return "-".join(self.user.roles)

            def _autosetup(self) -> RpcBrokerConfig.Autosetup | None:
                if self.device_id is None:
                    return None
                return next(
                    (
                        setup
                        for setup in self.config.autosetups
                        if setup.roles & set(self.user.roles)
                        and any(
                            fnmatch.fnmatchcase(self.device_id, did)
                            for did in setup.device_id
                        )
                    ),
                    None,
                )

            def mount_point(  # noqa D102
                self, existing: collections.abc.Set[str] = frozenset()
            ) -> str | None:
                if self._mount_point is None and (autosetup := self._autosetup()):
                    assert self.device_id is not None
                    return autosetup.generate_mount_point(
                        existing, self.device_id, self.user
                    )
                return self._mount_point

            def initial_subscriptions(self) -> collections.abc.Iterator[str]:  # noqa D102
                if autosetup := self._autosetup():
                    yield from autosetup.subscriptions

            def access_level(self, path: str, method: str) -> RpcAccess | None:  # noqa PLR6301
                return nmax(
                    self.config.roles[r].access_level(path, method)
                    for r in self.user.roles
                )

    @dataclasses.dataclass
    class Connect:
        """Connection to be established to some other peer."""

        url: RpcUrl
        """RPC URL specifying the connection destination."""
        roles: list[str] = dataclasses.field(default_factory=list)
        """Roles assigned to this connection."""
        mount_point: str | None = None
        """Mount point for this connection."""
        subscriptions: set[str] = dataclasses.field(default_factory=set)
        """Set of subscriptions to be automatically prepared for this connection."""

        class Role(RpcBrokerRoleABC):
            """The role for the connections."""

            def __init__(
                self, config: RpcBrokerConfig, connection: RpcBrokerConfig.Connect
            ) -> None:
                self.config = config
                self.connection = connection

            @property
            def name(self) -> str:  # noqa D102
                return "+".join(self.connection.roles)

            def mount_point(  # noqa D102
                self, existing: collections.abc.Set[str] = frozenset()
            ) -> str | None:
                return self.connection.mount_point

            def initial_subscriptions(self) -> collections.abc.Iterator[str]:  # noqa D102
                yield from self.connection.subscriptions

            def access_level(self, path: str, method: str) -> RpcAccess | None:  # noqa PLR6301
                return nmax(
                    self.config.roles[r].access_level(path, method)
                    for r in self.connection.roles
                )

    def __init__(
        self,
        name: str = "",
        listen: collections.abc.Iterable[RpcUrl] = frozenset(),
        connect: collections.abc.Iterable[RpcBrokerConfig.Connect] = frozenset(),
        roles: collections.abc.Iterable[RpcBrokerConfig.Role] = frozenset(),
        users: collections.abc.Iterable[RpcBrokerConfig.User] = frozenset(),
        autosetups: collections.abc.Iterable[RpcBrokerConfig.Autosetup] = frozenset(),
    ) -> None:
        self._name = name
        self.listen: list[RpcUrl] = list(listen)
        """List of server URLs where broker should listen for peers."""
        self.connect: list[RpcBrokerConfig.Connect] = list(connect)
        """List of connections broker should establish."""
        self.roles: NamedMap[RpcBrokerConfig.Role] = NamedMap(roles)
        """Role descriptions for this configuration."""
        self.users: NamedMap[RpcBrokerConfig.User] = NamedMap(users)
        """Users available in this configuration."""
        self.autosetups: list[RpcBrokerConfig.Autosetup] = list(autosetups)
        """Sequence of autosetup rules."""

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RpcBrokerConfig)
            and self.name == other.name
            and self.listen == other.listen
            and self.connect == other.connect
            and self.roles == other.roles
            and self.users == other.users
            and self.autosetups == other.autosetups
        )

    def __repr__(self) -> str:
        return repr({
            "name": self._name,
            "listen": self.listen,
            "connect": self.connect,
            "roles": self.roles,
            "users": self.users,
            "autosetups": self.autosetups,
        })

    @property
    def name(self) -> str:  # noqa D102
        return self._name

    def listens(self) -> collections.abc.Iterator[RpcUrl]:
        """Iterate over URLs where Broker should listen to."""
        yield from self.listen

    def connections(
        self,
    ) -> collections.abc.Iterator[tuple[RpcUrl, RpcBrokerRoleABC]]:
        """Iterate over URLs and their setup where Broker should connect to."""
        for connect in self.connect:
            yield connect.url, connect.Role(self, connect)

    def login(self, login: RpcLogin, nonce: str) -> RpcBrokerRoleABC | None:  # noqa D102
        if (user := self.users.get(login.username, None)) and login.validate_password(
            user.password, nonce, user.login_type
        ):
            if login.device_mount_point is not None and not any(
                fnmatch.fnmatchcase(login.device_mount_point, dmp)
                for dmp in itertools.chain(
                    *(self.roles[r].mount_points for r in user.roles)
                )
            ):
                raise ValueError("Mount point is not allowed")
            return self.User.Role(self, user, login.device_id, login.device_mount_point)
        return None

    @classmethod
    def load(cls, path: pathlib.Path) -> RpcBrokerConfig:
        """Read configuration from file.

        :param file: Path to the configuration file.
        :return: Broker configuration instance.
        :raise RpcBrokerConfigurationError: When there is an issue in the configuration.
        """
        with path.open("rb") as f:
            data = tomllib.load(f)

        res = cls(str(data.pop("name", "")))
        res.listen = cls._load_urls(data.pop("listen", []), "listen")

        if connects := data.pop("connect", {}):
            if not isinstance(connects, collections.abc.Sequence):
                raise RpcBrokerConfigurationError("'connect' must be array")
            for i, connect in enumerate(connects):
                if not isinstance(connect, collections.abc.MutableMapping):
                    raise RpcBrokerConfigurationError(f"'connect[{i}]' must be table")
                url = connect.pop("url", None)
                if not isinstance(url, str):
                    raise RpcBrokerConfigurationError(
                        f"'connect[{i}].url' must be string and provided"
                    )
                con = cls.Connect(RpcUrl.parse(url))
                con.roles = cls._load_strlist(
                    connect.pop("role", []), f"connect[{i}].role"
                ) or ["default"]
                if (mount_point := connect.pop("mountPoint", None)) is not None:
                    con.mount_point = str(mount_point)
                con.subscriptions = cls._load_ris(
                    connect.pop("subscriptions", []), f"connect[{i}].subscriptions"
                )
                res.connect.append(con)

        if users := data.pop("user", {}):
            if not isinstance(users, collections.abc.Mapping):
                raise RpcBrokerConfigurationError("'user' must be table")
            for name, user in users.items():
                if (password := user.pop("password", None)) is not None:
                    login_type = RpcLoginType.PLAIN
                elif (password := user.pop("sha1pass", None)) is not None:
                    login_type = RpcLoginType.SHA1
                else:
                    raise RpcBrokerConfigurationError(
                        f"'user.{name}.password' must be specfied"
                    )
                uroles = cls._load_strlist(
                    user.pop("role", []), f"user.{name}.role"
                ) or ["default"]
                res.users.add(cls.User(name, str(password), uroles, login_type))
                if user:
                    raise RpcBrokerConfigurationError(
                        f"'user.{name}' invalid table keys: {', '.join(user)}"
                    )

        if roles := data.pop("role", {}):
            if not isinstance(roles, collections.abc.Mapping):
                raise RpcBrokerConfigurationError("'role' must be table")
            for name, role in roles.items():
                r = cls.Role(name)
                if (mount_points := role.pop("mountPoints", None)) is not None:
                    if isinstance(mount_points, str):
                        mount_points = [mount_points]
                    if not isinstance(mount_points, collections.abc.Sequence):
                        raise RpcBrokerConfigurationError(
                            f"'role.{name}.mountPoints' must be array of strings"
                        )
                    r.mount_points = {str(v) for v in mount_points}
                if (access := role.pop("access", None)) is not None:
                    if not isinstance(access, collections.abc.Mapping):
                        raise RpcBrokerConfigurationError(
                            f"'role.{name}.access' must be table"
                        )
                    for level, paths in access.items():
                        nlevel = RpcAccess.strmap().get(level)
                        if nlevel is None:
                            raise RpcBrokerConfigurationError(
                                f"'{level} is not allowed in 'role.{name}.access'"
                            )
                        if not isinstance(paths, collections.abc.Sequence):
                            raise RpcBrokerConfigurationError(
                                f"'role.{name}.access.{level}' must be array"
                            )
                        r.access[nlevel] = {
                            str(v)
                            for v in ([paths] if isinstance(paths, str) else paths)
                        }
                if role:
                    raise RpcBrokerConfigurationError(
                        f"'role.{name}' invalid table keys: {', '.join(role)}"
                    )
                res.roles.add(r)

        if autosetups := data.pop("autosetup", []):
            if not isinstance(autosetups, collections.abc.Sequence):
                raise RpcBrokerConfigurationError("'role' must be array")
            for i, autosetup in enumerate(autosetups):
                if not isinstance(autosetup, collections.abc.MutableMapping):
                    raise RpcBrokerConfigurationError(f"'autosetup[{i}]' must be table")
                ast = cls.Autosetup(
                    cls._load_strset(
                        autosetup.pop("deviceId", []), f"autosetup[{i}].deviceId"
                    )
                )
                ast.roles = cls._load_strset(
                    autosetup.pop("role", []), f"autosetup[{i}].role"
                )
                if (mount_point := autosetup.pop("mountPoint", None)) is not None:
                    ast.mount_point = str(mount_point)
                ast.subscriptions = cls._load_ris(
                    autosetup.pop("subscriptions", []), f"autosetup[{i}].subscriptions"
                )
                res.autosetups.append(ast)

        if data:
            raise RpcBrokerConfigurationError(f"Invalid table keys: {', '.join(data)}")

        return res

    @staticmethod
    def _load_strarr(value: object, location: str) -> collections.abc.Iterator[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, collections.abc.Sequence) or any(
            not isinstance(v, str) for v in value
        ):
            raise RpcBrokerConfigurationError(f"'{location}' must be array of strings")
        yield from value

    @classmethod
    def _load_strlist(cls, value: object, location: str) -> list[str]:
        return list(cls._load_strarr(value, location))

    @classmethod
    def _load_strset(cls, value: object, location: str) -> set[str]:
        return set(cls._load_strarr(value, location))

    @classmethod
    def _load_urls(cls, value: object, location: str) -> list[RpcUrl]:
        return [RpcUrl.parse(sub) for sub in cls._load_strarr(value, location)]

    @classmethod
    def _load_ris(cls, value: object, location: str) -> set[str]:
        # TODO possibly validate RIs
        return {sub for sub in cls._load_strarr(value, location)}


class RpcBrokerConfigurationError(ValueError):
    """The error in the configuration."""
