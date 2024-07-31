"""Resource identification matching in SHV RPC.

This is implemented according to the `SHV standard documentation
<https://silicon-heaven.github.io/shv-doc/rpcri.html>`__.
"""

from __future__ import annotations

import fnmatch

from .value import SHVType


def rpcri_match(ri: str, path: str, method: str, signal: str | None = None) -> bool:
    """Check if given path or method matches given RPC RI.

    This can use used to match method or signal against RI.

    :param ri: RPC RI that should be used to match method or signal.
    :param path: SHV Path that that RI should match.
    :param method: SHV RPC method name that RI should match.
    :param signal: SHV RPC signal name that RI should match. This can be
      ``NULL`` and in such case RI matches method (``PATH:METHOD``) or non-empty
      string for signal matching (``PATH:METHOD:SIGNAL``).
    :return: ``True`` if RI matches the provided method or signal and ``False``
      otherwise.
    """
    parts = ri.split(":")
    match len(parts):
        case 2:
            return (
                signal is None
                and shvpath_match(parts[0], path)
                and fnmatch.fnmatchcase(method, parts[1])
            )
        case 3:
            return (
                signal is not None
                and shvpath_match(parts[0], path)
                and fnmatch.fnmatchcase(method, parts[1])
                and fnmatch.fnmatchcase(signal, parts[2])
            )
    return False


def rpcri_relative_to(ri: str, path: str) -> str | None:
    """Derive the RPC RI that is relative to the given path.

    :param ri: RPC RI that should be modified to be relative to the given path.
    :param path: Path that must be used as a relative root.
    :return: New RPC RI or ``None`` in case RI is not relative to the path.
    """
    pth, sep, rest = ri.partition(":")
    npth = shvpath_tail(pth, path)
    return f"{npth}{sep}{rest}" if npth is not None else None


def rpcri_legacy_subscription(ri: str) -> SHVType:
    """Convert RPC RI to legacy SHV subscription representation.

    :param ri: RPC RI for signal matching that should be converted.
    :return: Legacy subscription description.
    """
    parts = ri.split(":")
    if len(parts) != 3:
        raise ValueError("Must be RPC RI for signals")
    path, method, signal = parts
    res: dict[str, SHVType] = {}
    pth, _, tail = path.rpartition("/")
    if "*" in pth or tail != "**":
        res["paths"] = path
    else:
        res["path"] = pth
    if "*" in signal and signal != "*":
        res["methods"] = signal
    else:
        res["method"] = "" if signal == "*" else signal
    if method != "*":
        res["source"] = method
    return res


def __pth_match(path: str, pattern: list[str]) -> int | None:
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


def shvpath_match(pattern: str, path: str) -> bool:
    """Check if given path matches given pattern.

    :param pattern: Pattern that should match the SHV path.
    :param path: SHV Path.
    :return: ``True`` if the whole path matches the pattern and ``False`` otherwise.
    """
    ptn = pattern.split("/")
    res = __pth_match(path, ptn)
    return res is not None and len(ptn) == res


def shvpath_tail(pattern: str, path: str) -> str | None:
    """Remove the pattern prefix that matches given path.

    :param pattern: Pattern for which tail should be derived.
    :param path: Path the pattern should match.
    :return: Returns tail that can be used to match nodes bellow path or ``None`` in
      case pattern doesn't match the path or matches it exactly.
    """
    ptn = pattern.split("/")
    res = __pth_match(path, ptn)
    if len(ptn) == res and ptn[-1] == "**":
        res -= 1
    if res is None or len(ptn) == res:
        return None
    return "/".join(ptn[res:])
