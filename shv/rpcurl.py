"""SHV RPC URL for RpcClient and RpcServer."""
import dataclasses
import enum
import getpass
import urllib.parse

from .value import SHVType


class RpcProtocol(enum.Enum):
    """Enum of supported RPC protocols by this Python implementation."""

    TCP = enum.auto()
    UDP = enum.auto()
    LOCAL_SOCKET = enum.auto()
    SERIAL = enum.auto()


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
    """

    # URL primary fields
    location: str
    """Hostname of the SHV RPC server or path to the socket.

    .. versionchanged:: 0.3.0
       This attribute was named ``host`` in version 0.2.0.
    """
    port: int = 3755
    """Port the SHV RPC server is listening on."""
    protocol: RpcProtocol = RpcProtocol.TCP
    """SHV RPC protocol used to communicate (This is scheme in URL therminology)"""
    username: str = getpass.getuser()
    """User name used to login to the remote server."""

    # Options
    password: str | None = None
    """Password used to login to the server."""
    login_type: RpcLoginType = RpcLoginType.SHA1
    """Type of the login to be used (specifies format of the password)."""
    device_id: str | None = None
    """Device identifier sent to the server with login."""
    device_mount_point: str | None = None
    """Request for mounting of connected device to the specified mount point."""
    baudrate: int = 115200
    """Baudrate used for some of the link protocols."""

    def login_options(self) -> dict[str, SHVType]:
        """Assemble login options for the SHV RPC broker from options here."""
        res: dict[str, SHVType] = {}
        if self.device_id:
            res["device"] = res.get("device", {})
            res["device"]["deviceId"] = self.device_id  # type: ignore
        if self.device_mount_point:
            res["device"] = res.get("device", {})
            res["device"]["mountPoint"] = self.device_mount_point  # type: ignore
        return res

    @classmethod
    def parse(cls, url: str) -> "RpcUrl":
        """Parse string URL to the object representation.

        :param url: URL in string format.
        :return: New :class:`RpcUrl` instance.
        """
        sr = urllib.parse.urlsplit(url, scheme="localsocket", allow_fragments=False)
        pqs = urllib.parse.parse_qs(sr.query)

        protocols = {
            "tcp": RpcProtocol.TCP,
            "udp": RpcProtocol.UDP,
            "localsocket": RpcProtocol.LOCAL_SOCKET,
            "unix": RpcProtocol.LOCAL_SOCKET,
            "serial": RpcProtocol.SERIAL,
            "serialport": RpcProtocol.SERIAL,
            "rs232": RpcProtocol.SERIAL,
        }
        if sr.scheme not in protocols:
            raise ValueError(f"Invalid scheme: {sr.scheme}")
        protocol = protocols[sr.scheme]

        res = cls("", protocol=protocol)

        res.username = sr.username or res.username
        if protocol in (RpcProtocol.TCP, RpcProtocol.UDP):
            res.location = sr.hostname or ""
            if sr.port is not None:
                res.port = int(sr.port)
            if sr.path:
                raise ValueError(f"Path is not supported for {sr.scheme}: {sr.path}")
        elif protocol in (RpcProtocol.LOCAL_SOCKET, RpcProtocol.SERIAL):
            res.location = f"/{sr.netloc}{sr.path}" if sr.netloc else sr.path
        else:
            raise NotImplementedError()  # pragma: no cover

        # We prefer SHA1 password and thus discard plain if both are present
        if opts := pqs.pop("shapass", []):
            res.password = opts[0]
            res.login_type = RpcLoginType.SHA1
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
            raise ValueError(f"Unsupported URL queries: {pqs.keys()}")

        return res

    def to_url(self) -> str:
        """Convert to string URL."""
        protocols = {
            RpcProtocol.TCP: "tcp",
            RpcProtocol.UDP: "udp",
            RpcProtocol.LOCAL_SOCKET: "localsocket",
        }
        if self.protocol in (RpcProtocol.TCP, RpcProtocol.UDP):
            netloc = "//"
            if self.username and self.username != type(self).username:
                netloc += f"{self.username}@"
            if ":" in self.location:
                netloc += f"[{self.location}]"
            else:
                netloc += self.location
            netloc += f":{self.port}"
        elif self.protocol is RpcProtocol.LOCAL_SOCKET:
            netloc = self.location
        else:
            raise NotImplementedError()  # pragma: no cover

        opts: list[str] = []
        if self.device_id:
            opts.append(f"devid={self.device_id}")
        if self.device_mount_point:
            opts.append(f"devmount={self.device_mount_point}")
        if self.password:
            if self.login_type is RpcLoginType.SHA1:
                # TODO escape password string?
                opts.append(f"shapass={self.password}")
            elif self.login_type is RpcLoginType.PLAIN:
                opts.append(f"password={self.password}")
            else:
                raise NotImplementedError()  # pragma: no cover
        if self.baudrate != type(self).baudrate:
            opts.append(f"baudrate={self.baudrate}")

        return (
            f"{protocols[self.protocol]}:{netloc}{'?' if opts else ''}{'&'.join(opts)}"
        )
