"""Abstraction on top of a single subscription."""

from __future__ import annotations

import dataclasses
import fnmatch

from .value import SHVType, is_shvmap


@dataclasses.dataclass(frozen=True)
class RpcSubscription:
    """Single SHV RPC subscription."""

    paths: str = "**"
    """Pattern for SHV path matching."""
    signal: str = "*"
    """Pattern for signal name subscription is applied on."""
    source: str = "*"
    """Pattern for method name signal must be associated with."""

    def applies(self, path: str, signal: str, source: str) -> bool:
        """Check if given subscription applies to this combination.

        :param path: SHV Path.
        :param signal: Signal name.
        :param source: Source method name.
        :return: Boolean depending on the way this subscription applies on given path
          and method.
        """
        return (
            path_match(path, self.paths)
            and fnmatch.fnmatchcase(signal, self.signal)
            and fnmatch.fnmatchcase(source, self.source)
        )

    def relative_to(self, path: str) -> RpcSubscription | None:
        """Get subscription that is relative to the given path.

        This is used to pass subscription to sub-brokers. It updates
        :param:`path` and/or :param:`paths` in such a way that it is applied
        relative to that path. ``None`` is returned if this subscription doesn't
        apply it.

        :param path: Path this sunscription should be fixed to.
        :return: New subscription that is relative to the given *path* or
          ``None``.
        """
        if not path:
            return self  # Relative to root
        if (pat := tail_pattern(path.rstrip("/"), self.paths)) is not None:
            return dataclasses.replace(self, paths=pat)
        return None

    @classmethod
    def from_shv(cls, value: SHVType) -> RpcSubscription:
        """Create subscription from SHV type representation."""
        if not is_shvmap(value):
            raise ValueError("Expected Map")
        # We intentionally ignore unknown keys here
        paths: SHVType = cls.paths
        if (path := value.get("path", None)) is not None:
            paths = f"{path}/**" if path else "**"
        paths = value.get("paths", paths)
        signal = value.get(
            "methods", value.get("method", value.get("signal", cls.signal))
        )
        source = value.get("source", cls.source)
        if (
            not isinstance(paths, str)
            or not isinstance(signal, str)
            or not isinstance(source, str)
        ):
            raise ValueError("Invalid type")
        return cls(paths, signal, source)

    def to_shv(self, compatible: bool = False) -> SHVType:
        """Convert to representation used in SHV RPC communication."""
        res: dict[str, SHVType] = {}
        if compatible:
            pth, _, tail = self.paths.rpartition("/")
            if "*" in pth or tail != "**":
                res["paths"] = self.paths
            else:
                res["path"] = pth
            if "*" in self.signal and self.signal != "*":
                res["methods"] = self.signal
            else:
                res["method"] = "" if self.signal == "*" else self.signal
        else:
            if self.paths != "**":
                res["paths"] = self.paths
            if self.signal != "*":
                res["signal"] = self.signal
        if self.source != "*":
            res["source"] = self.source
        return res

    @classmethod
    def from_str(cls, value: str) -> RpcSubscription:
        """Create subscription from common string representation.

        This representation is simply ``PATH:SIGNAL:SOURCE`` where everything
        except ``PATH`` is optional. If you want to use default ``SIGNAL`` but
        specify ``SOURCE`` then you can use ``PATH::SOURCE``

        :param value: The string representation to be interpreted.
        :return: New object representing this subscription.
        """
        p, _, ns = value.partition(":")
        n, _, s = ns.partition(":")
        return cls(p, n if n else cls.signal, s if s else cls.source)

    def to_str(self) -> str:
        """Convert to common string representation.

        Please see :meth:`fromStr`.
        """
        # TODO do not add unnecessary fields
        return f"{self.paths}:{self.signal}:${self.source}"


DefaultRpcSubscription = RpcSubscription()


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
