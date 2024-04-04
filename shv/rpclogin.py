"""RPC client specific functions to login to the RPC Broker."""

import copy
import dataclasses
import enum
import functools
import getpass
import hashlib
import logging
import typing

from .value import SHVMapType, SHVType, is_shvmap

logger = logging.getLogger(__name__)

T = typing.TypeVar("T")


@functools.lru_cache
def _get_user() -> str:
    # getuser fails if there is no account assigned to the UID in the system
    try:
        return getpass.getuser()
    except KeyError:
        return "none"


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
    force_plain: bool = False
    """Forces plain login when PLAIN is specified as *login_type*.

    The default behavior when working with login is to elevate plain logins to
    SHA1 for somewhat increased security but that prevents from PLAIN login to
    be tested and thus this option exists.
    """

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
        # TODO remove on None
        self.__dictmerge({"device": {"deviceId": value}}, self.options)

    @property
    def device_mount_point(self) -> str | None:
        """Request for mounting of connected device to the specified mount point."""
        return self.__dictget(self.options, str, "device", "mountPoint")

    @device_mount_point.setter
    def device_mount_point(self, value: str | None) -> None:
        # TODO remove on None
        self.__dictmerge({"device": {"mountPoint": value}}, self.options)

    def extended_options(self, extend: dict[str, SHVType]) -> dict[str, SHVType]:
        """Extend passed options with those specified here.

        This is handy if you have your options and only need to fill standard
        ones provided by this class.

        :param extend: Dictionary to be extended.
        :return: The *extend* dictionary. This is for convenience, the passed
          dictionary is always returned with modifications.
        """
        self.__dictmerge(self.options, extend)
        return extend

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
            else:
                dest[k] = copy.deepcopy(v)
        return dest

    def param(self, nonce: str, custom_options: SHVMapType | None = None) -> SHVType:
        """RPC Login parameter.

        :param nonce: The string with random characters returned from hello
          method call.
        :param custom_options: These are additional options to be added to the
          login options.
        :return: Parameters to be passed to login method call.
        """
        password = self.password
        login_type = self.login_type
        if self.login_type is RpcLoginType.PLAIN and not self.force_plain:
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
