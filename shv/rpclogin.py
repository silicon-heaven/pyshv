"""RPC client specific functions to login to the RPC Broker."""

from __future__ import annotations

import copy
import dataclasses
import enum
import functools
import getpass
import hashlib
import logging
import typing

from .rpcerrors import RpcInvalidParamError
from .rpcparam import shvgett
from .value import SHVMapType, SHVType, is_shvmap

logger = logging.getLogger(__name__)

T = typing.TypeVar("T")


@functools.lru_cache
def _get_user() -> str:
    # getuser fails if there is no account assigned to the UID in the system
    try:
        return getpass.getuser()
    except KeyError:  # pragma: no cover
        return "nobody"


class RpcLoginType(enum.Enum):
    """Enum specifying which login type should be used.

    The string values are the exact string representation used in SHV RPC
    protocol identifying these login types.
    """

    PLAIN = "PLAIN"
    """Plain login format should be used."""
    SHA1 = "SHA1"
    """Use hash algorithm SHA1 (preferred and common default)."""


@dataclasses.dataclass
class RpcLogin:
    """SHV RPC Broker login info.

    This is all in one login info for user.
    """

    username: str = dataclasses.field(default=_get_user())
    """User name used to login to the remote server."""
    password: str = ""
    """Password used to login to the server."""
    login_type: RpcLoginType = RpcLoginType.PLAIN
    """Type of the login to be used (specifies format of the password)."""
    options: dict[str, SHVType] = dataclasses.field(default_factory=dict)
    """Additional options passed with login to the RPC Broker to configure session."""

    opt_device_id: dataclasses.InitVar[str | None] = None
    opt_device_mount_point: dataclasses.InitVar[str | None] = None

    def __post_init__(
        self, opt_device_id: str | None, opt_device_mount_point: str | None
    ) -> None:
        if opt_device_id is not None:
            self.device_id = opt_device_id
        if opt_device_mount_point is not None:
            self.device_mount_point = opt_device_mount_point

    @property
    def device_id(self) -> str | None:
        """Device identifier sent to the server with login."""
        return self.__dictget(self.options, str, "device", "deviceId")

    @device_id.setter
    def device_id(self, value: str | None) -> None:
        self.__dictmerge({"device": {"deviceId": value}}, self.options)

    @property
    def device_mount_point(self) -> str | None:
        """Request for mounting of connected device to the specified mount point."""
        return self.__dictget(self.options, str, "device", "mountPoint")

    @device_mount_point.setter
    def device_mount_point(self, value: str | None) -> None:
        self.__dictmerge({"device": {"mountPoint": value}}, self.options)

    @property
    def idle_timeout(self) -> int | None:
        """Request for specific setting of the idle timeout on the broker."""
        return self.__dictget(self.options, int, "idleWatchDogTimeOut")

    @idle_timeout.setter
    def idle_timeout(self, value: int | None) -> None:
        self.__dictmerge({"idleWatchDogTimeOut": value}, self.options)

    def extend_options(self, options: dict[str, SHVType]) -> None:
        """Merge passed options with curent ones.

        This is handy if you have your options and only need to fill standard
        ones provided by this class.

        :param options: Dictionary with items used to extend options.
        """
        self.__dictmerge(options, self.options)

    def validate_password(
        self, password: str, nonce: str, login_type: RpcLoginType = RpcLoginType.PLAIN
    ) -> bool:
        """Validate this login against given password and nonce.

        The arguments passed to this method are for the expected password that
        user should provide. The password can be either in plain text or hashed
        with SHA1.

        :param password: The reference password.
        :param nonce: Nonce used for SHA1 login.
        :param login_type: The format of the password.
        """
        rpass = self.password
        match login_type, self.login_type:
            case RpcLoginType.PLAIN, RpcLoginType.PLAIN:
                pass
            case RpcLoginType.PLAIN, RpcLoginType.SHA1:
                password = hashlib.sha1(password.encode("utf-8")).hexdigest()  # noqa PLR6301
                login_type = RpcLoginType.SHA1
            case RpcLoginType.SHA1, RpcLoginType.PLAIN:
                rpass = hashlib.sha1(  # noqa PLR6301
                    nonce.encode("utf-8")
                    + hashlib.sha1(rpass.encode("utf-8")).hexdigest().encode("utf-8")  # noqa PLR6301
                ).hexdigest()
            case RpcLoginType.SHA1, RpcLoginType.SHA1:
                pass
            case _, _:  # pragma: no cover
                return False
        match login_type:
            case RpcLoginType.PLAIN:
                return rpass == password
            case RpcLoginType.SHA1:
                m = hashlib.sha1()  # noqa PLR6301
                m.update(nonce.encode("utf-8"))
                m.update(password.encode("utf-8"))  # password must be SHA1
                return rpass == m.hexdigest()
            case _:  # pragma: no cover
                raise NotImplementedError

    @classmethod
    def __dictget(cls, src: SHVType, tp: type[T], *key: str) -> T | None:
        if not key:
            return src if isinstance(src, tp) else None
        if not is_shvmap(src) or key[0] not in src:
            return None
        return cls.__dictget(src[key[0]], tp, *key[1:])

    @classmethod
    def __dictmerge(
        cls, src: SHVMapType, dest: dict[str, SHVType]
    ) -> dict[str, SHVType]:
        for k, v in src.items():
            if (
                is_shvmap(v)
                and isinstance((destk := dest.get(k, None)), dict)
                and all(isinstance(k, str) for k in destk)
            ):
                cls.__dictmerge(v, destk)
                if not destk:
                    dest.pop(k, None)
            elif cls.__notnone(v):
                dest[k] = copy.deepcopy(v)
            else:
                dest.pop(k, None)
        return dest

    @classmethod
    def __notnone(cls, value: SHVType) -> bool:
        if not is_shvmap(value):
            return value is not None
        return all(cls.__notnone(v) for v in value.values())

    def to_shv(
        self,
        nonce: str,
        custom_options: SHVMapType | None = None,
        trusted: bool = False,
    ) -> SHVType:
        """RPC Login parameter in the parameter format for login method.

        :param nonce: The string with random characters returned from hello
          method call that is used for SHA1 login.
        :param custom_options: These are additional options to be added to the
          login options.
        :param trusted: Specifies if the transport can be trusted. On untrusted
          transport layers the `SHA1` password is used even if this login
          specifies `PLAIN`.
        :return: Parameters to be passed to login method call.
        """
        password = self.password
        login_type = self.login_type
        if self.login_type is RpcLoginType.PLAIN and not trusted:
            login_type = RpcLoginType.SHA1
            password = hashlib.sha1(self.password.encode("utf-8")).hexdigest()  # noqa S324
        if login_type is RpcLoginType.SHA1:
            m = hashlib.sha1()  # noqa S324
            m.update(nonce.encode("utf-8"))
            m.update((password or "").encode("utf-8"))
            password = m.hexdigest()
        return {
            "login": {
                "password": password,
                "type": login_type.value,
                "user": self.username,
            },
            "options": typing.cast(
                SHVType,
                self.__dictmerge(
                    self.options, copy.deepcopy(dict(custom_options or {}))
                ),
            ),
        }

    @classmethod
    def from_shv(cls, value: SHVType) -> RpcLogin:
        """Create from SHV RPC login method parameter.

        :param value: The value that was received as login method parameter.
        :return: The :class:`RpcLogin` object.
        :raise RpcInvalidParamError: If parameter is invalid in some way.
        """
        if not is_shvmap(value):
            raise RpcInvalidParamError("Expected Map.")
        username = shvgett(value, ("login", "user"), str, "")
        password = shvgett(value, ("login", "password"), str, "")
        login_type = RpcLoginType(
            shvgett(
                value,
                ("login", "type"),
                str,
                RpcLoginType.SHA1.value
                if len(password) == 40
                else RpcLoginType.PLAIN.value,
            )
        )
        options = value.get("options")
        if not is_shvmap(options):
            options = {}
        return cls(username, password, login_type, dict(options))
