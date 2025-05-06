"""SHV RPC URL used to specify connection and listen settings."""

import dataclasses
import enum
import functools
import getpass
import urllib.parse

from .rpclogin import RpcLogin, RpcLoginType


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
    TTY = enum.auto()
    """Serial transport layer."""
    WS = enum.auto()
    """WebSockets transport layer."""
    WSS = enum.auto()
    """WebSockets secure transport layer."""


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
    """Hostname of the SHV RPC server or path to the socket."""
    port: int = -1
    """Port the SHV RPC server is listening on."""
    protocol: RpcProtocol = RpcProtocol.TCP
    """SHV RPC protocol used to communicate (This is scheme in URL therminology)"""
    login: RpcLogin = dataclasses.field(default_factory=RpcLogin)
    """Parameters for RPC Broker login."""

    # TTY
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
            "serial": RpcProtocol.TTY,
            "tty": RpcProtocol.TTY,
            "ws": RpcProtocol.WS,
            "wss": RpcProtocol.WSS,
        }
        if sr.scheme not in protocols:
            raise ValueError(f"Invalid scheme: {sr.scheme}")
        protocol = protocols[sr.scheme]

        res = cls("", protocol=protocol)

        res.login.username = sr.username or res.login.username
        match protocol:
            case (
                RpcProtocol.TCP | RpcProtocol.TCPS | RpcProtocol.SSL | RpcProtocol.SSLS
            ):
                res.location = sr.hostname or ""
                if sr.port is not None:
                    res.port = int(sr.port)
                if sr.path:
                    raise ValueError(f"Path not supported for {sr.scheme}: {sr.path}")
            case RpcProtocol.UNIX | RpcProtocol.UNIXS | RpcProtocol.TTY:
                res.location = f"/{sr.netloc}{sr.path}" if sr.netloc else sr.path
            case RpcProtocol.WS | RpcProtocol.WSS:
                if sr.path:
                    if sr.port is not None:
                        raise ValueError(
                            "Port can't be specified with path for websockets"
                        )
                    res.location = f"{sr.netloc}{sr.path}"
                else:
                    res.location = sr.hostname or ""
                    if sr.port is not None:
                        res.port = int(sr.port)
            case protocol:
                raise NotImplementedError(f"Protocol: {protocol}")  # pragma: no cover

        if opts := pqs.pop("user", []):
            res.login.username = opts[0]
        if opts := pqs.pop("shapass", []):
            if len(opts[0]) != 40:
                raise ValueError("SHA1 password must have 40 characters.")
            res.login.password = opts[0]
            res.login.login_type = RpcLoginType.SHA1
            # We prefer SHA1 password and thus discard plain if both are present
            pqs.pop("password", [])
        elif opts := pqs.pop("password", []):
            res.login.password = opts[0]
            res.login.login_type = RpcLoginType.PLAIN
        if opts := pqs.pop("devid", []):
            res.login.device_id = opts[0]
        if opts := pqs.pop("devmount", []):
            res.login.device_mount_point = opts[0]
        if protocol is RpcProtocol.TTY:
            if opts := pqs.pop("baudrate", []):
                res.baudrate = int(opts[0])

        if pqs:
            raise ValueError(f"Unsupported URL queries: {', '.join(pqs.keys())}")

        return res

    def to_url(self, public: bool = False) -> str:
        """Convert to string URL.

        :param public: You can pass ``True`` to not include login credentials.
        :returns: The string representation of the RPC URL.
        """
        protocols = {
            RpcProtocol.TCP: "tcp",
            RpcProtocol.TCPS: "tcps",
            RpcProtocol.SSL: "ssl",
            RpcProtocol.SSLS: "ssls",
            RpcProtocol.UNIX: "unix",
            RpcProtocol.UNIXS: "unixs",
            RpcProtocol.TTY: "serial",
            RpcProtocol.WS: "ws",
            RpcProtocol.WSS: "wss",
        }
        user_added = not self.login.username or self.login.username == RpcLogin.username
        match self.protocol:
            case (
                RpcProtocol.TCP | RpcProtocol.TCPS | RpcProtocol.SSL | RpcProtocol.SSLS
            ):
                netloc = "//"
                if not user_added:
                    netloc += f"{self.login.username}@"
                    user_added = True
                if ":" in self.location:
                    netloc += f"[{self.location}]"
                else:
                    netloc += self.location
                netloc += f":{self.port}"
            case RpcProtocol.UNIX | RpcProtocol.UNIXS | RpcProtocol.TTY:
                netloc = self.location
            case RpcProtocol.WS | RpcProtocol.WSS:
                if self.port == type(self).port:
                    netloc = self.location
                else:
                    netloc = "//"
                    if not user_added:
                        netloc += f"{self.login.username}@"
                        user_added = True
                    if ":" in self.location:
                        netloc += f"[{self.location}]"
                    else:
                        netloc += self.location
                    netloc += f":{self.port}"
            case protocol:
                raise NotImplementedError(f"Protocol: {protocol}")  # pragma: no cover

        opts: list[str] = []
        if not user_added:
            opts.append(f"user={urllib.parse.quote(self.login.username)}")
            user_added = True
        if self.login.device_id:
            opts.append(f"devid={urllib.parse.quote(self.login.device_id)}")
        if self.login.device_mount_point:
            opts.append(f"devmount={urllib.parse.quote(self.login.device_mount_point)}")
        if self.login.password and not public:
            if self.login.login_type is RpcLoginType.SHA1:
                opts.append(f"shapass={self.login.password}")
            elif self.login.login_type is RpcLoginType.PLAIN:
                opts.append(f"password={urllib.parse.quote(self.login.password)}")
            else:
                raise NotImplementedError()  # pragma: no cover
        if self.baudrate != type(self).baudrate:
            opts.append(f"baudrate={self.baudrate}")

        return (
            f"{protocols[self.protocol]}:{netloc}{'?' if opts else ''}{'&'.join(opts)}"
        )
