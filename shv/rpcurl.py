"""SHV RPC URL used to specify connection and listen settings."""

import dataclasses
import enum
import functools
import getpass
import pathlib
import ssl
import typing
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

    # SSL
    ca: str | pathlib.Path | None = None
    """CA certificates."""
    cert: str | pathlib.Path | None = None
    """Certificate."""
    key: str | pathlib.Path | None = None
    """Secret part of client certificate."""
    crl: str | pathlib.Path | None = None
    """Certificate revocation list for server."""
    verify: bool | None = None
    """If peer verifies is required.

    For server this enforces clients verification (clients need their own
    certificate).

    For client this enforces server verification.

    The default is different between server and client. It is ``true`` for
    client and ``false`` for server and thus default is ``None``.
    """

    # TTY
    baudrate: int = 115200
    """Baudrate used for some of the link protocols."""

    default_port: typing.ClassVar[dict[RpcProtocol, int]] = {
        RpcProtocol.TCP: 3755,
        RpcProtocol.TCPS: 3765,
        RpcProtocol.SSL: 3756,
        RpcProtocol.SSLS: 3766,
    }

    def __post_init__(self) -> None:
        """Deduce the correct value for port."""
        if self.port == type(self).port:
            self.port = self.default_port.get(self.protocol, self.port)

    def __str__(self) -> str:
        return self.to_url()

    def ssl_server(self) -> ssl.SSLContext:
        """Create :class:`ssl.SSLContext` for server."""
        if self.protocol not in {RpcProtocol.SSL, RpcProtocol.SSLS}:
            raise ValueError("Not supported for this protocol")
        if self.ca is None:
            raise ValueError("'ca' must be provided")
        if self.cert is None:
            raise ValueError("'cert' must be provided")
        if self.key is None:
            raise ValueError("'key' must be provided")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=self.cert, keyfile=self.key)
        context.load_verify_locations(cafile=self.ca)
        if self.crl is not None:
            context.load_verify_locations(cafile=self.crl)
            context.verify_flags = ssl.VERIFY_CRL_CHECK_LEAF
        context.verify_mode = (
            ssl.CERT_REQUIRED if self.verify is True else ssl.CERT_OPTIONAL
        )
        return context

    def ssl_client(self) -> ssl.SSLContext:
        """Create :class:`ssl.SSLContext` for client."""
        if self.protocol not in {RpcProtocol.SSL, RpcProtocol.SSLS}:
            raise ValueError("Not supported for this protocol")
        cacheck = self.verify is not False
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if cacheck:
            if self.ca is None:
                raise ValueError("'ca' must be provided")
            context.load_verify_locations(cafile=self.ca)
        if self.cert is not None and self.key is not None:
            context.load_cert_chain(certfile=self.cert, keyfile=self.key)
        context.check_hostname = cacheck
        context.verify_mode = ssl.CERT_REQUIRED if cacheck else ssl.CERT_NONE
        return context

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

        if opts := pqs.pop("token", []):
            res.login.token = opts[0]
            res.login.login_type = RpcLoginType.TOKEN
        else:
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
        if protocol in {RpcProtocol.SSL, RpcProtocol.SSLS}:
            if opts := pqs.pop("ca", []):
                res.ca = opts[0]
            if opts := pqs.pop("cafile", []):
                res.ca = pathlib.Path(opts[0])
            if opts := pqs.pop("cert", []):
                res.cert = opts[0]
            if opts := pqs.pop("certfile", []):
                res.cert = pathlib.Path(opts[0])
            if opts := pqs.pop("key", []):
                res.key = opts[0]
            if opts := pqs.pop("keyfile", []):
                res.key = pathlib.Path(opts[0])
            if opts := pqs.pop("crl", []):
                res.crl = opts[0]
            if opts := pqs.pop("crlfile", []):
                res.crl = pathlib.Path(opts[0])
            if opts := pqs.pop("verify", []):
                if opts[0] in {"true", "t"}:
                    res.verify = True
                elif opts[0] in {"false", "f"}:
                    res.verify = False
                else:
                    raise ValueError(f"Invalid for verify: {opts[0]}")
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
                if self.port != self.default_port[self.protocol]:
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
        if not public:
            if self.login.token:
                opts.append(f"token={self.login.token}")
            if self.login.password:
                if self.login.login_type is RpcLoginType.SHA1:
                    opts.append(f"shapass={self.login.password}")
                elif self.login.login_type is RpcLoginType.PLAIN:
                    opts.append(f"password={urllib.parse.quote(self.login.password)}")
                else:
                    raise NotImplementedError()  # pragma: no cover
        if self.baudrate != type(self).baudrate:
            opts.append(f"baudrate={self.baudrate}")
        if self.ca != type(self).ca:
            opts.append(
                f"{'cafile' if isinstance(self.ca, pathlib.Path) else 'ca'}={self.ca}"
            )
        if self.cert != type(self).cert:
            opts.append(
                f"{'certfile' if isinstance(self.cert, pathlib.Path) else 'cert'}={self.cert}"
            )
        if self.key != type(self).key:
            opts.append(
                f"{'keyfile' if isinstance(self.key, pathlib.Path) else 'key'}={self.key}"
            )
        if self.crl != type(self).crl:
            opts.append(
                f"{'crlfile' if isinstance(self.crl, pathlib.Path) else 'crl'}={self.crl}"
            )
        if self.verify != type(self).verify:
            opts.append(f"verify={'true' if self.verify else 'false'}")

        return (
            f"{protocols[self.protocol]}:{netloc}{'?' if opts else ''}{'&'.join(opts)}"
        )
