Implementing Device
===================

Devices are clients that provide some SHV tree of nodes and thus allow others to
call their methods. The biggest complication is to actually allow clients to
discover device's nodes and methods. This requires ``ls`` and ``dir`` methods
implemnetation for every node.

The device implementation should be a new Python class based on
:class:`shv.SimpleClient`.


Listing nodes
-------------

This is implementation of ``ls`` method. In :class:`shv.SimpleClient` you need
to override :meth:`shv.SimpleClient._ls` method and implement it. It needs to
return iterator over tuples where first value in tuple is name of the child node
and second value is boolean signaling if there are any more children.

The simple example for tree like this follows::

   ├── status
   └── track
       ├── 1
       └── 2


.. sourcecode::

   def _ls(self, path: str) -> collections.abc.Sequence[tuple[str, bool]]:
       pth = path.split("/") if path else []
       if len(pth) == 0:
           yield ("status", False)
           yield ("track", True)
           return
       if pth[0] == "status" and len(pth) == 1:
           return
       elif pth[0] == "track":
           if len(pth) == 1:
               yield ("1", False)
               yield ("2", False)
               return
           if len(pth) == 2 and pth[1] in ("1", "2"):
               return
       return super()._ls(path)

The base implementation raises exception :class:`shv.RpcMethodNotFoundError`
(with exception to the root path) and thus you should call it for any path that
points to no valid node. You need to make sure that you don't yield any value
before this exception is raised because this method is used also to detect node
existence with code ``next(self._ls(path())``.


Listing methods
---------------

To implement ``dir`` method you need to override :meth:`shv.SimpleClient._dir`
method and implement generator providing method descriptions. This method is
called only if :meth:`shv.SimpleClient._ls` does not report
:exc:`shv.RpcMethodNotFoundError` for the same path.

.. sourcecode::

    def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        pth = path.split("/") if path else []
        if len(pth) == 2 and pth[0] == "track" and pth[1] in self.tracks:
            yield RpcMethodDesc.getter(result="List[Int]", description="List of tracks")
            yield RpcMethodDesc.setter(param="List[Int]", description="Set track")

The base implementation should be always called right at the start because it
provides standard methods such as ``ls`` and ``dir``.


Methods implementation
----------------------

Now when clients can discover our SHV tree and our methods we need to actually
implement them. This is done by overriding method
:meth:`shv.SimpleClient._method_call`.

The implementation is pretty strait forward. You get SHV path and method name as
arguments alongside parameters and you need to return result or raise exception.

For an example see the next section.


The complete example
--------------------

.. literalinclude:: ../example_device.py
