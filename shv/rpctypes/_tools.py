"""Common tools for SHV RPC type definitions."""

import decimal


def strnum(num: int | None) -> str:
    """Convert number to string representation."""
    if num is None:
        return ""
    if abs(num) >= 100:  # Not worth it for two digits
        blen = num.bit_length()
        if blen == num.bit_count():
            return f">{'-' if num < 0 else ''}{blen}"
        if (1 << (blen - 1)) == abs(num):
            return f"^{'-' if num < 0 else ''}{blen - 1}"
    return str(num)


def strdec(num: decimal.Decimal | None) -> str:
    """Convert number to string representation."""
    if num is None:
        return ""
    result = str(num)
    if result.startswith("0."):
        return result[1:]
    if result.startswith("-0."):
        return f"-{result[2:]}"
    return result
