"""SHV RPC URL for RpcClient and RpcServer."""
import dataclasses
import enum
import functools
import getpass
import urllib.parse

from .value import SHVType


@functools.lru_cache
def _get_user() -> str:
    # getuser fails if there is no account assigned to the UID in the system
    try:
        return getpass.getuser()
    except KeyError:
        return "none"


class RpcProtocol(enum.Enum):
    """Enum of supported RPC protocols by this Python implementation."""

    TCP = enum.auto()
    """TCP/IP with messages transported using Stream transport layer."""
    TCPS = enum.auto()
    """TCP/IP with messages transported using Serial transport layer."""
    SSL = enum.auto()
    """TLS TCP/IP with messages transported using Stream transport layer."""
    SSLS = enum.auto()
    """TLS TCP/IP with messages transported using Serial transport layer."""
    UNIX = enum.auto()
    """Unix local domain named socket using Stream transport layer."""
    UNIXS = enum.auto()
    """Unix local domain named socket using Reliable Serial transport layer."""
    SERIAL = enum.auto()
    """Serial transport layer."""


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
class RpcUrl:
    """SHV RPC URL specifier.

    This is unified locator for SHV RPC connections that is used to specify
    connections. It is implemented as :func:`dataclasses.dataclass` and you
    can set properties directly or you can parse string URL.

    The URL format is defined in `SHV standard
    <https://silicon-heaven.github.io/shv-doc/rpcurl.html>`_.
    """

    # URL primary fields
    location: str
    """Hostname of the SHV RPC server or path to the socket.

    .. versionchanged:: 0.3.0
       This attribute was named ``host`` in version 0.2.0.
    """
    port: int = -1
    """Port the SHV RPC server is listening on."""
    protocol: RpcProtocol = RpcProtocol.TCP
    """SHV RPC protocol used to communicate (This is scheme in URL therminology)"""
    username: str = _get_user()
    """User name used to login to the remote server."""

    # Options
    password: str = ""
    """Password used to login to the server."""
    login_type: RpcLoginType = RpcLoginType.PLAIN
    """Type of the login to be used (specifies format of the password)."""
    device_id: str | None = None
    """Device identifier sent to the server with login."""
    device_mount_point: str | None = None
    """Request for mounting of connected device to the specified mount point."""
    baudrate: int = 115200
    """Baudrate used for some of the link protocols."""

    def __post_init__(self) -> None:
        """Deduce the correct value for port."""
        if self.port == type(self).port:
            self.port = {
                RpcProtocol.TCP: 3755,
                RpcProtocol.TCPS: 3765,
                RpcProtocol.SSL: 3756,
                RpcProtocol.SSLS: 3766,
            }.get(self.protocol, self.port)

    def login_options(self) -> dict[str, SHVType]:
        """Assemble login options for the SHV RPC broker from options here."""
        res: dict[str, SHVType] = {}
        if self.device_id:
            res["deviceId"] = self.device_id
        if self.device_mount_point:
            res["mountPoint"] = self.device_mount_point
        return {"device": res} if res else {}

    def __str__(self) -> str:
        return self.to_url()

    @classmethod
    def parse(cls, url: str) -> "RpcUrl":
        """Parse string URL to the object representation.

        :param url: URL in string format.
        :return: New :class:`RpcUrl` instance.
        :raise ValueError: when invalid URL is passed.
        """
        sr = urllib.parse.urlsplit(url, scheme="unix", allow_fragments=False)
        pqs = urllib.parse.parse_qs(sr.query)

        protocols = {
            "tcp": RpcProtocol.TCP,
            "tcps": RpcProtocol.TCPS,
            "ssl": RpcProtocol.SSL,
            "ssls": RpcProtocol.SSLS,
            "unix": RpcProtocol.UNIX,
            "unixs": RpcProtocol.UNIXS,
            "serial": RpcProtocol.SERIAL,
            "tty": RpcProtocol.SERIAL,
        }
        if sr.scheme not in protocols:
            raise ValueError(f"Invalid scheme: {sr.scheme}")
        protocol = protocols[sr.scheme]

        res = cls("", protocol=protocol)

        res.username = sr.username or res.username
        if protocol in (
            RpcProtocol.TCP,
            RpcProtocol.TCPS,
            RpcProtocol.SSL,
            RpcProtocol.SSLS,
        ):
            res.location = sr.hostname or ""
            if sr.port is not None:
                res.port = int(sr.port)
            if sr.path:
                raise ValueError(f"Path is not supported for {sr.scheme}: {sr.path}")
        elif protocol in (RpcProtocol.UNIX, RpcProtocol.UNIXS, RpcProtocol.SERIAL):
            res.location = f"/{sr.netloc}{sr.path}" if sr.netloc else sr.path
        else:
            raise NotImplementedError  # pragma: no cover

        if opts := pqs.pop("user", []):
            res.username = opts[0]
        if opts := pqs.pop("shapass", []):
            if len(opts[0]) != 40:
                raise ValueError("SHA1 password must have 40 characters.")
            res.password = opts[0]
            res.login_type = RpcLoginType.SHA1
            # We prefer SHA1 password and thus discard plain if both are present
            pqs.pop("password", [])
        elif opts := pqs.pop("password", []):
            res.password = opts[0]
            res.login_type = RpcLoginType.PLAIN
        if opts := pqs.pop("devid", []):
            res.device_id = opts[0]
        if opts := pqs.pop("devmount", []):
            res.device_mount_point = opts[0]
        if protocol is RpcProtocol.SERIAL:
            if opts := pqs.pop("baudrate", []):
                res.baudrate = int(opts[0])

        if pqs:
            raise ValueError(f"Unsupported URL queries: {', '.join(pqs.keys())}")

        return res

    def to_url(self) -> str:
        """Convert to string URL."""
        protocols = {
            RpcProtocol.TCP: "tcp",
            RpcProtocol.TCPS: "tcps",
            RpcProtocol.SSL: "ssl",
            RpcProtocol.SSLS: "ssls",
            RpcProtocol.UNIX: "unix",
            RpcProtocol.UNIXS: "unixs",
            RpcProtocol.SERIAL: "serial",
        }
        user_added = not self.username or self.username == type(self).username
        if self.protocol in (
            RpcProtocol.TCP,
            RpcProtocol.TCPS,
            RpcProtocol.SSL,
            RpcProtocol.SSLS,
        ):
            netloc = "//"
            if not user_added:
                netloc += f"{self.username}@"
                user_added = True
            if ":" in self.location:
                netloc += f"[{self.location}]"
            else:
                netloc += self.location
            netloc += f":{self.port}"
        elif self.protocol in (RpcProtocol.UNIX, RpcProtocol.UNIXS, RpcProtocol.SERIAL):
            netloc = self.location
        else:
            raise NotImplementedError  # pragma: no cover

        opts: list[str] = []
        if not user_added:
            opts.append(f"user={urllib.parse.quote(self.username)}")
            user_added = True
        if self.device_id:
            opts.append(f"devid={urllib.parse.quote(self.device_id)}")
        if self.device_mount_point:
            opts.append(f"devmount={urllib.parse.quote(self.device_mount_point)}")
        if self.password:
            if self.login_type is RpcLoginType.SHA1:
                opts.append(f"shapass={self.password}")
            elif self.login_type is RpcLoginType.PLAIN:
                opts.append(f"password={urllib.parse.quote(self.password)}")
            else:
                raise NotImplementedError()  # pragma: no cover
        if self.baudrate != type(self).baudrate:
            opts.append(f"baudrate={self.baudrate}")

        return (
            f"{protocols[self.protocol]}:{netloc}{'?' if opts else ''}{'&'.join(opts)}"
        )
