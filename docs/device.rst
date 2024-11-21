Implementing Device
===================

Devices are clients that provide some SHV tree of nodes and thus allow others to
call their methods. The biggest complication is to actually allow clients to
discover device's nodes and methods. This requires ``ls`` and ``dir`` methods
implemnetation for every node.

The device implementation should be a new Python class based on
:class:`shv.SHVClient` or :class:`shv.SHVDevice` (for physical devices). There
is also :class:`shv.SHVMethods` you can add to allow easier method
implementation.

.. warning::
   There are two concepts of "device" in SHV. One is RPC Device which is client
   mounted in SHV RPC Broker. The second is the physical device representation.
   This document talks about the first concept not the second one and thus you
   should use :class:`shv.SHVBase` or :class:`shv.SHVClient` and not
   :class:`shv.SHVDevice`, unless you really have physical device that this
   application manages.

.. tip::
   Devices can be also implemented with `SHVTree
   <https://silicon-heaven.gitlab.io/shvtree/>`_.


Methods
-------

Methods are the core building block of the SHV RPC. Probably the easiest way to
implement methods callable over SHV RPC is usage of
:meth:`shv.SHVMethods.method`. This is a decorated that can be used only in
classes based on :class:`shv.SHVMethods`. It ensures that method is correctly
discoverable and callable. You don't have to check the access level or presence
of a user's ID as that is verified based on the provided method description.

.. sourcecode::

   @SHVMethods.method("somePath", RpcMethodDesc.getter("custom", signal=True))
   def custom(self, request: SHVBase.Request) -> SHVType:
        return "CustomResult"

Methods can also have signals associated with them. Decorated method provides
:meth:`shv.SHVMethods.Method.signal` that can be called to send that signal.
Thus in case of demonstrated example you would use ``await
mclient.custom.signal("NewCustomValue")`` to send ``chng`` signal with provided
value. This will send first defined signal but you can also specify which signal
to send with ``signal`` argument if multiple signals were defined for the method
in its descriptor.

Properties
----------

Properties are the most notable repeated pattern of methods that SHV RPC define.
They consists of node with ``get`` method and optional ``set`` method.

:class:`shv.SHVMethods` provides convenient way to define them.

.. sourcecode::

   @SHVMethods.property("customProp", signal=True)
   def custom_prop(self, oldness: int | None) -> SHVType:
       return self.prop

   @SHVMethods.property_setter(custom_prop)
   async def custom_prop_set(self, param: SHVType, user_id: str | None) -> None:
       self.prop = param

The signal associated with the property can be sent the same way as for other
methods: ``await mclient.custom_prop.signal("NewPropValue")``. Note that signal
is in no situation emited automatically and thus it must be sent explicitly by
calling ``signal`` method as described.

Dynamic methods definition
--------------------------

The dynamic way of defining methods is the underlying implementation used by
:class:`shv.SHVMethods` and thus you can use it to implement nodes and methods
that are dynamic, but it is also the implementation way if you decide not to use
:class:`shv.SHVMethods`.

Listing nodes
^^^^^^^^^^^^^

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

There is also an helper :meth:`shv.SHVBase._ls_node_for_path` to implement
:meth:`shv.SHVBase._ls` that you might want to use to not have to write code
that correctly splits paths to the nodes.


Listing methods
^^^^^^^^^^^^^^^

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
^^^^^^^^^^^^^^^^^^^^^^

Now when clients can discover our SHV tree and our methods we need to actually
implement them. This is done by overriding method
:meth:`shv.SHVBase._method_call`.

The implementation is pretty strait forward. You get SHV path and method name,
parameter, optional user's ID, and access level in :class:`shv.SHVBase.Request`.
The access level needs to be checked if user has required access level. The
implementation needs to return result or raise exception (preferably one of
:class:`shv.shv.RpcError` children) or call the parent's implementation.

For an example see the next section.


The complete example
--------------------

.. literalinclude:: ../example_device.py
