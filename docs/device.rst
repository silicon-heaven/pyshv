Implementing Device
===================

Devices are clients that provide some SHV tree of nodes and thus allow others to
call their methods. The biggest complication is to actually allow clients to
discover device's nodes and methods. This requires ``ls`` and ``dir`` methods
implemnetation for every node.

The device implementation should be a new Python class based on
:class:`shv.SimpleBase` or :class:`shv.SimpleDevice` (for physical devices).

.. warning::
   There are two concepts of "device" in SHV. One is RPC Device which is client
   mounted in SHV RPC Broker. The second is the physical device representation.
   This document talks about the first concept not the second one and thus you
   should use :class:`shv.SimpleBase` and not :class:`shvSimpleDevice`, unless
   you really have physical interface that this client controls.

.. tip::
   Devices can be more easilly implemented with
   `SHVTree <https://elektroline-predator.gitlab.io/shvtree/>`_.


Listing nodes
-------------

This is implementation of ``ls`` method. In :class:`shv.BaseClient` you need to
override :meth:`shv.BaseClient._ls` method and implement it. It needs to return
iterator over child nodes. Do not forget to also yield base implementation.

The simple example for tree like this follows::

   ├── status
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

To implement ``dir`` method you need to override :meth:`shv.SimpleBase._dir`
method and implement generator providing method descriptions. This method is
called only if :meth:`shv.SimpleBase._ls` reports this node as existing one.

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
:meth:`shv.SimpleBase._method_call`.

The implementation is pretty strait forward. You get SHV path and method name as
arguments alongside parameters and you need to return result or raise exception
(preferably one of :class:`shv.RpcError` children).

For an example see the next section.


The complete example
--------------------

.. literalinclude:: ../example_device.py
