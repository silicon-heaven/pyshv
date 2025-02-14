"""The extension for the PurePosixPath to support our root."""

from __future__ import annotations

import collections.abc
import itertools
import os
import string
import typing

from .rpcri import shvpath_match


class SHVPath:
    """The SHV path helper.

    This is designed to be close to the :mod:`pathlib` while providing the SHV
    path specific behavior. But some of the methods just doesn't make sense in
    the respect of the SHV path (such as ``is_absolute``).

    We can't easily use :mod:`pathlib` based version because there are huge
    differences in the implementation (not external API) between Python 3.11
    and 3.12 and later versions.

    The rules for the SHV path are:

    - White characters (like spaces) are not allowed.
    - SHV path can't be absolute (can't start with ``/``).
    - ``""`` is parent of every path.
    - The combination of SHV path and string representing an absolute path
      (appending absolute path to SHV) results into only absolute path being
      used (while leading ``/`` is removed). This behavior is not derived from
      SHV path but rather from :mod:`pathlib`.
    - ``..`` is being interpreted as upped directory and thus removes upper
      node from the SHV path. This is extension of the standard SHV path
      behavior as SHV standard do not specify ``..`` interpretation.
    """

    def __init__(self, *pathsegments: str | os.PathLike) -> None:
        parts: list[str] = []
        for segment in itertools.chain.from_iterable(
            os.fspath(pth).split("/") for pth in pathsegments if pth
        ):
            if any(c in segment for c in string.whitespace):
                raise ValueError("SHV path can't contain white space characters")
            if segment == "..":
                if parts:
                    parts.pop()
            elif segment:
                parts.append(segment)
            else:
                parts = []
        self._parts = tuple(parts)

        self._parents: SHVPathParents | None = None
        self._hash: int | None = None

    @property
    def parts(self) -> tuple[str, ...]:
        """Tuple giving access to the path's various components."""
        return self._parts

    def __str__(self) -> str:
        return "/".join(self._parts)

    def __fspath__(self) -> str:
        return str(self)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)!r})"

    def __reduce__(self) -> tuple[type[SHVPath], tuple[str, ...]]:
        return self.__class__, tuple(self._parts)  # pragma: no coverage

    def __bool__(self) -> bool:
        return bool(self._parts)

    def __truediv__(self, key: str | os.PathLike | SHVPath) -> SHVPath:
        return type(self)(*self._parts, key)

    def __rtruediv__(self, key: str | os.PathLike) -> SHVPath:
        return type(self)(key, *self._parts)

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(tuple(self._parts))
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str | os.PathLike):
            return os.fspath(self) == os.fspath(other)
        return super().__eq__(other)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, str | os.PathLike):
            return os.fspath(self) < os.fspath(other)
        raise TypeError(f"unsupported '<' between '{type(self)}' and '{type(other)}'")

    def __le__(self, other: object) -> bool:
        if isinstance(other, str | os.PathLike):
            return os.fspath(self) <= os.fspath(other)
        raise TypeError(f"unsupported '<=' between '{type(self)}' and '{type(other)}'")

    def __gt__(self, other: object) -> bool:
        if isinstance(other, str | os.PathLike):
            return os.fspath(self) > os.fspath(other)
        raise TypeError(f"unsupported '>' between '{type(self)}' and '{type(other)}'")

    def __ge__(self, other: object) -> bool:
        if isinstance(other, str | os.PathLike):
            return os.fspath(self) >= os.fspath(other)
        raise TypeError(f"unsupported '>=' between '{type(self)}' and '{type(other)}'")

    @property
    def parents(self) -> SHVPathParents:
        """An immutable sequence providing access to the logical ancestors of the path."""
        if self._parents is None:
            self._parents = SHVPathParents(self)
        return self._parents

    @property
    def parent(self) -> SHVPath:
        """The logical parent of the path."""
        if self._parts:
            return type(self)(*self._parts[:-1])
        return self

    @property
    def name(self) -> str:
        """A string representing the final path component, if any."""
        return self._parts[-1] if self._parts else ""

    @property
    def suffix(self) -> str:
        """The last dot-separated portion of the final component, if any."""
        _, dot, suffix = self.name.rpartition(".")
        return f"{dot}{suffix}"

    @property
    def suffixes(self) -> list[str]:
        """The last dot-separated portion of the final component, if any."""
        return list(f".{s}" for s in self.name.split(".")[1:])

    @property
    def stem(self) -> str:
        """The final path component, without its suffix."""
        return self.name.partition(".")[0]

    def is_relative_to(self, path: str | os.PathLike | SHVPath) -> bool:
        """Return whether or not this path is relative to the other path."""
        if not isinstance(path, SHVPath):
            path = SHVPath(path)
        return path._parts == self._parts[: len(path._parts)]

    def joinpath(self, *pathsegments: str | os.PathLike) -> SHVPath:
        """Join paths together.

        Calling this method is equivalent to combining the path with each of
        the given path segments in turn.
        """
        return type(self)(*self._parts, *pathsegments)

    def full_match(self, pattern: str) -> bool:
        """Match this path against the provided glob-style pattern."""
        return shvpath_match(pattern, str(self))

    def match(self, pattern: str) -> bool:
        """Match this path against the provided glob-style pattern."""
        return any(
            shvpath_match(pattern, "/".join(parts))
            for parts in map(lambda i: self._parts[i:], range(len(self._parts)))
        )

    def relative_to(self, other: str | os.PathLike | SHVPath) -> SHVPath:
        """Compute a version of this path relative to the path represented by other."""
        if not isinstance(other, SHVPath):
            other = SHVPath(other)
        if self._parts[: len(other._parts)] != other._parts:
            raise ValueError(f"{self} is not relative to {other}")
        return SHVPath(*self._parts[len(other._parts) :])

    def with_name(self, name: str) -> SHVPath:
        """Return a new path with the name changed."""
        if not self._parts:
            raise ValueError("Root path has an empty name.")
        return type(self)(*self._parts[:-1], name)

    def with_stem(self, stem: str) -> SHVPath:
        """Return a new path with the stem changed."""
        if not self._parts:
            raise ValueError("Root path has an empty name.")
        _, dot, suffix = self._parts[-1].partition(".")
        return type(self)(*self._parts[:-1], f"{stem}{dot}{suffix}")

    def with_suffix(self, suffix: str) -> SHVPath:
        """Return a new path with the suffix changed."""
        if not self._parts:
            raise ValueError("Root path has an empty name.")
        return type(self)(*self._parts[:-1], f"{self.stem}{suffix}")


class SHVPathParents(collections.abc.Sequence[SHVPath]):
    """The parents generator for :class:`SHVPath`."""

    def __init__(self, path: SHVPath) -> None:
        self._path = path

    @typing.overload
    def __getitem__(self, i: int) -> SHVPath: ...

    @typing.overload
    def __getitem__(
        self, i: slice[typing.Any, typing.Any, typing.Any]
    ) -> collections.abc.Sequence[SHVPath]: ...

    def __getitem__(
        self, i: int | slice[typing.Any, typing.Any, typing.Any]
    ) -> collections.abc.Sequence[SHVPath] | SHVPath:
        parts = self._path.parts
        if isinstance(i, slice):
            return tuple(self[y] for y in range(*i.indices(len(parts))))

        if -len(parts) <= i < len(parts):
            return SHVPath(*parts[: -i - 1])
        raise IndexError("index out of range for SHV path parent")

    def __len__(self) -> int:
        return len(self._path.parts)
