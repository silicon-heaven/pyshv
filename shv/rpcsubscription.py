"""Abstraction on top of a single subscription."""
from __future__ import annotations

import collections.abc
import dataclasses
import fnmatch
import typing

from .value import SHVMapType, SHVType


@dataclasses.dataclass(frozen=True)
class RpcSubscription:
    """Single SHV RPC subscription."""

    path: str = ""
    """SHV Path the subscription is applied on."""
    method: str = "chng"
    """Method name subscription is applied on."""
    paths: str | None = None
    """Pattern that replaces the **path** match. Compared to the **path** the patter
    must match exactly and thus it can be used to subscribed only on a signle node.

    **path** is ignored if this is not ``None``.
    """
    methods: str | None = None
    """Pattern that replaces **method**. It must match method exactly to apply.

    **method** is ignored if this is not ``None``.
    """

    def applies(self, path: str, method: str) -> bool:
        """Check if given subscription applies to this combination.

        :param path: SHV Path.
        :param method: Method name.
        :return: Boolean depending on the way this subscription applies on given path
          and method.
        """
        path_matches: bool
        if self.paths is not None:
            path_matches = path_match(path, self.paths)
        else:
            path_matches = (
                not self.path
                or path.startswith(self.path)
                and (len(path) == len(self.path) or path[len(self.path)] == "/")
            )
        method_matches: bool
        if self.methods is not None:
            method_matches = fnmatch.fnmatch(method, self.methods)
        else:
            method_matches = not self.method or method == self.method
        return path_matches and method_matches

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
        if self.paths is not None:
            if pat := tail_pattern(path, self.paths):
                return dataclasses.replace(self, paths=pat)
            return None
        p = path.rstrip("/") + ("/" if path else "")
        sp = self.path.rstrip("/") + ("/" if self.path else "")
        if sp.startswith(p):
            return dataclasses.replace(self, path=sp[len(p) : -1])
        return None

    @classmethod
    def fromSHV(cls, value: SHVType) -> "RpcSubscription":
        """Create subscription from SHV type representation."""
        if not isinstance(value, collections.abc.Mapping):
            raise ValueError("Expected Map")
        value = typing.cast(SHVMapType, value)
        # We ignore unknown keys here intentionally
        path = value.get("path", cls.path)
        method = value.get("method", cls.method)
        paths = value.get("paths", cls.paths)
        methods = value.get("methods", cls.methods)
        if (
            not isinstance(path, str)
            or not isinstance(method, str)
            or not isinstance(paths, (str, type(None)))
            or not isinstance(methods, (str, type(None)))
        ):
            raise ValueError("Invalid type")
        return cls(path, method, paths, methods)

    def toSHV(self) -> SHVType:
        """Convert to representation used in SHV RPC communication."""
        res: dict[str, SHVType] = {}
        if self.paths is not None:
            res["paths"] = self.paths
        elif self.path:
            res["path"] = self.path
        if self.methods is not None:
            res["methods"] = self.methods
        else:
            res["method"] = self.method
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
            elif fnmatch.fnmatch(node, pattern[i + 1]):
                i += 2
            continue
        if not fnmatch.fnmatch(node, pattern[i]):
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
    """Remove the longest pattern prefix that matches given path.

    The tail can match more nodes if they would be added to the path.

    :param path: Path the pattern should match.
    :param pattern: Pattern to be split.
    :return: Returns tail that can be used to match nodes bellow path or ``None`` in
      case pattern doesn't match the path.
    """
    ptn = pattern.split("/")
    res = __match(path, ptn)
    if len(ptn) == res and ptn[-1] == "**":
        res -= 1
    if res is None or len(ptn) == res:
        return None
    return "/".join(ptn[res:])
