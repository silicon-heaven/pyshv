"""Tests for cli utility."""
import subprocess
import sys


def subprocess_foo(*args):
    """Run foo as subprocess and return subprocess handle for it."""
    return subprocess.Popen(
        [sys.executable, "-m", "foo", *args],
        env={"PYTHONPATH": ":".join(sys.path)},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_stdin():
    """Check that we can feed data from stdin."""
    with subprocess_foo() as subproc:
        out, err = subproc.communicate(b"foo: once\nNo foo\nfoo:twice\nTerminate")
        assert err == b""
        assert out == b"2\n"


def test_files(tmpdir):
    """Check that we can feed data from files."""
    src1 = tmpdir.join("src1")
    src2 = tmpdir.join("src2")
    src1.write_binary(b"\nNothing\nfoo: once\nNone")
    src2.write_binary(b"foo: twice")
    with subprocess_foo(src1, src2) as subproc:
        out, err = subproc.communicate(b"foo: once\nNo foo\nfoo:twice\nTerminate")
        assert err == b""
        assert out == b"2\n"
