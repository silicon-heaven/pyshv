"""Resource identification matching in SHV RPC.

This is implemented according to the `SHV standard documentation
<https://silicon-heaven.github.io/shv-doc/rpcri.html>`__.
"""

from __future__ import annotations

import dataclasses
import fnmatch

from .value import SHVType, is_shvmap


@dataclasses.dataclass(frozen=True)
class RpcRI:
    """Resource identification in SHV RPC.

    This is used to create matching rules for methods as well as signals.
    Examples are subscriptions in RPC Broker or access control in the Broker.
    """

    path: str = "**"
    """Pattern for SHV path matching."""
    method: str = "*"
    """Pattern for method name matching."""
    signal: str = "*"
    """Pattern for signal name matching."""

    def __str__(self) -> str:
        if self.signal == type(self).signal:
            if self.method == type(self).method:
                return self.path
            return f"{self.path}:{self.method}"
        method = self.method if self.method != "get" else ""
        return f"{self.path}:{method}:{self.signal}"

    def match(self, path: str, method: str, signal: str = "") -> bool:
        """Check if this resource identifier matches.

        For method call matching you must keep ``signal`` to default, that is
        empty string.

        :param path: SHV path to the resource.
        :param method: Method name for the resource match.
        :param signal: Signal name for the resource match.
        :return: ``True`` if matches and ``False`` otherwise.
        """
        return (
            path_match(path, self.path)
            and fnmatch.fnmatchcase(method, self.method)
            and fnmatch.fnmatchcase(signal, self.signal)
        )

    def relative_to(self, path: str) -> RpcRI | None:
        """Deduce RPC RI that is relative to the given path.

        This is used to pass subscription to sub-brokers. It updates
        :param:`path` in such a way that it is applied relative to that path.
        ``None`` is returned if this resource identification doesn't apply it.

        :param path: Path this sunscription should be fixed to.
        :return: New subscription that is relative to the given *path* or
          ``None``.
        """
        if not path:
            return self  # Relative to root
        if (pat := tail_pattern(path.rstrip("/"), self.path)) is not None:
            return dataclasses.replace(self, path=pat)
        return None

    @classmethod
    def parse(cls, value: str) -> RpcRI:
        """Create RPC RI from common string representation.

        This representation is simply ``PATH:METHOD:SIGNAL`` where everything
        except ``PATH`` is optional. If you want to use default ``METHOD``
        ``get`` but specify ``SIGNAL`` then you can use ``PATH::SIGNAL``

        :param value: The string representation to be interpreted.
        :return: New object representing this RPC RI.
        """
        p, d, ms = value.partition(":")
        if d == ":":
            m, d, s = ms.partition(":")
            if d == ":":
                return cls(p, m if m else "get", s if s else cls.signal)
            return cls(p, m)
        return cls(p)

    @classmethod
    def from_subscription(cls, value: SHVType) -> tuple[RpcRI, int | None]:
        """Create RPC RI for subscription from SHV type representation."""
        if not is_shvmap(value):
            raise ValueError("Expected Map")
        # We intentionally ignore unknown keys here
        paths: SHVType = RpcRI.path
        if (path := value.get("path", None)) is not None:
            paths = f"{path}/**" if path else "**"
        paths = value.get("paths", paths)
        method = value.get("source", RpcRI.method)
        # Note: the methods here is misleading but it backward compatible for
        # implementations that viewed signal as a method and not as something
        # associated with method.
        signal = value.get(
            "methods", value.get("method", value.get("signal", RpcRI.signal))
        )
        ttl = value.get("ttl", None)
        if (
            not isinstance(paths, str)
            or not isinstance(method, str)
            or not isinstance(signal, str)
            or (not isinstance(ttl, int) and ttl is not None)
        ):
            raise ValueError("Invalid type")
        return cls(paths, method, signal), ttl

    def to_subscription(
        self, ttl: int | None = None, compatible: bool = False
    ) -> SHVType:
        """Convert to representation Subscription used in SHV RPC communication."""
        res: dict[str, SHVType] = {}
        if compatible:
            pth, _, tail = self.path.rpartition("/")
            if "*" in pth or tail != "**":
                res["paths"] = self.path
            else:
                res["path"] = pth
            if "*" in self.signal and self.signal != "*":
                res["methods"] = self.signal
            else:
                res["method"] = "" if self.signal == "*" else self.signal
        else:
            if self.path != "**":
                res["paths"] = self.path
            if self.signal != "*":
                res["signal"] = self.signal
            if ttl is not None:
                res["ttl"] = ttl
        if self.method != "*":
            res["source"] = self.method
        return res


def __match(path: str, pattern: list[str]) -> int | None:
    i = 0
    for node in path.split("/"):
        if i >= len(pattern):
            return None
        if pattern[i] == "**":
            if len(pattern) == i + 1:
                return i + 1  # Matches everything so just return
            if pattern[i + 1] == "**":
                i += 1
            elif fnmatch.fnmatchcase(node, pattern[i + 1]):
                i += 2
            continue
        if not fnmatch.fnmatchcase(node, pattern[i]):
            return None
        i += 1
    return i


def path_match(path: str, pattern: str) -> bool:
    """Check if given path matches given pattern.

    :param path: SHV Path.
    :param pattern: Pattern that should match the SHV path.
    :return: ``True`` if the whole path matches the pattern and ``False`` otherwise.
    """
    ptn = pattern.split("/")
    res = __match(path, ptn)
    return res is not None and len(ptn) == res


def tail_pattern(path: str, pattern: str) -> str | None:
    """Remove the pattern prefix that matches given path.

    :param path: Path the pattern should match.
    :param pattern: Pattern to be split.
    :return: Returns tail that can be used to match nodes bellow path or ``None`` in
      case pattern doesn't match the path or matches it exactly.
    """
    ptn = pattern.split("/")
    res = __match(path, ptn)
    if len(ptn) == res and ptn[-1] == "**":
        res -= 1
    if res is None or len(ptn) == res:
        return None
    return "/".join(ptn[res:])
