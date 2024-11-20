Implementing Device
===================

Devices are clients that provide some SHV tree of nodes and thus allow others to
call their methods. The biggest complication is to actually allow clients to
discover device's nodes and methods. This requires ``ls`` and ``dir`` methods
implemnetation for every node.

The device implementation should be a new Python class based on
:class:`shv.SHVClient` or :class:`shv.SHVDevice` (for physical devices).

.. warning::
   There are two concepts of "device" in SHV. One is RPC Device which is client
   mounted in SHV RPC Broker. The second is the physical device representation.
   This document talks about the first concept not the second one and thus you
   should use :class:`shv.SHVBase` or :class:`shv.SHVClient` and not
   :class:`shv.SHVDevice`, unless you really have physical device that this
   application manages.

.. tip::
   Devices can be more easilly implemented with `SHVTree
   <https://silicon-heaven.gitlab.io/shvtree/>`_. That removes common
   errors where :meth:`shv.SHVBase._dir` and
   :meth:`shv.SHVBase._method_call` implementations are not in synch and thus
   method is described as being different than actually is.


Listing nodes
-------------

This is implementation of ``ls`` method. In :class:`shv.SHVBase` you need to
override :meth:`shv.SHVBase._ls` method and implement it. It needs to return
iterator over child nodes. Do not forget to also yield base implementation with
`yield from super()._ls(path)`.

The simple example for tree like this follows::

   ├── .app
   └── track
       ├── 1
       └── 2


.. sourcecode::

   def _ls(self, path: str) -> collections.abc.Sequence[tuple[str, bool]]:
        yield from super()._ls(path)
        if path == "":
            yield "track"
        elif path == "track":
            yield "1"
            yield "2"


Listing methods
---------------

To implement ``dir`` method you need to override :meth:`shv.SHVBase._dir`
method and implement generator providing method descriptions. This method is
called only if :meth:`shv.SHVBase._ls` reports this node as existing one. Do
not forget to first yield base implementation with `yield from
super()._dir(path)` to provide standard methods such as ``ls`` and ``dir``.

.. sourcecode::

    def _dir(self, path: str) -> collections.abc.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        pth = path.split("/") if path else []
        if len(pth) == 2 and pth[0] == "track" and pth[1] in self.tracks:
            yield RpcMethodDesc.getter(result="List[Int]", description="List of tracks")
            yield RpcMethodDesc.setter(param="List[Int]", description="Set track")


Methods implementation
----------------------

Now when clients can discover our SHV tree and our methods we need to actually
implement them. This is done by overriding method
:meth:`shv.SHVBase._method_call`.

The implementation is pretty strait forward. You get SHV path and method name,
optional user's ID, and access level as arguments alongside parameter. The
access level needs to be checked if user has required access level. The
implementation needs to return result or raise exception (preferably one of
:class:`shv.RpcError` children) or call the parent's implementation.

For an example see the next section.


The complete example
--------------------

.. literalinclude:: ../example_device.py
