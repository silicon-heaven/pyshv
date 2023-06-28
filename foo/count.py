# Copyright (C) 2023 Elektroline Inc. All rights reserved.
# K Ladvi 1805/20
# Prague, 184 00
# info@elektroline.cz (+420 284 021 111)
"""The 'foo' counting module."""
import typing


def count_foo(file: typing.TextIO) -> int:
    """Count number of lines starting with 'foo:'."""
    return sum(1 if line.startswith("foo:") else 0 for line in file)
