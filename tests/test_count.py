"""Tests for foos counting module."""
import io

import pytest

from foo import count_foo


@pytest.mark.parametrize(
    ("text", "expected_count"),
    (
        ("foo: something", 1),
        ("something", 0),
        ("something foo: fee", 0),
    ),
)
def test_text(text, expected_count):
    """Check that we correctly count foos in provided text."""
    with io.StringIO(text) as file:
        assert count_foo(file) == expected_count
