Implementing Device
===================

Devices are clients that provide some SHV tree of nodes and thus allow others to
call their methods. The biggest complication is to actually allow clients to
discover device's nodes and methods. This requires ``ls`` and ``dir`` methods
implemnetation for every node.

The device implementation should be a new Python class based on
:class:`shv.DeviceClient`.


Listing nodes
-------------

This is implementation of ``ls`` method. In :class:`shv.DeviceClient` you need
to override :func:`shv.DeviceClient._ls` method and implement it. It needs to
return list of tuples where first value in tuple is name of the child node and
second value is boolean signaling if there are any more children.

The simple example for tree like this follows::

   ├── status
   └── track
       ├── 1
       └── 2


.. sourcecode::

   async def _ls(self, path: str) -> collections.abc.Sequence[tuple[str, bool]] | None:
       pth = path.split("/") if path else []
       if len(pth) == 0:
           return [("status", False), ("track", True)]
       if pth[0] == "status" and len(pth) == 1:
           return []
       elif pth[0] == "track":
           if len(pth) == 1:
               return [("1", False), ("2", False)]
           if len(pth) == 2 and pth[1] in ("1", "2"):
               return []
       return await super()._ls(path)


Listing methods
---------------

Methods should be possible to list for all existing nodes as reported by
``_ls``. You need to specify a bit more for methods but in general ``_dir``
implementations can be very close to the ``_ls`` one.

The default implementation is a bit smarter here compared to the ``_ls`` one. It
calls ``_ls`` to check if path is valid or not and if it is it won't return
``None``.

.. sourcecode::

    async def _dir(
        self, path: str
    ) -> collections.abc.Sequence[
        tuple[str, RpcMethodSignature, RpcMethodFlags, str, str]
    ] | None:
        pth = path.split("/") if path else []
        if pth[0] == "track":
            if len(pth) == 1:
                return []
            if len(pth) == 2 and pth[1] in ("1", "2"):
                return [
                    (
                        "get",
                        RpcMethodSignature.RET_VOID,
                        RpcMethodFlags.GETTER,
                        "rd",
                        "Get current track",
                    ),
                    (
                        "set",
                        RpcMethodSignature.VOID_PARAM,
                        RpcMethodFlags.SETTER,
                        "wr",
                        "Set track",
                    ),
                ]
        return await super()._dir(path)

Notice that we return list of tuples where fields have special meaning. You need
to always specify all fields. The meaning behind tuple fields is:

1. Name of the method
2. Signature saying if method returns some value and/or expects some parameter
3. Flags that are used to identify methods
4. Access right for the method
5. Description of the method


Methods implementation
----------------------

Now when clients can discover our SHV tree and our methods we need to actually
implement them. This is done by overriding method
:func:`shv.SimpleClient._method_call`.

The implementation is pretty strait forward. You get SHV path and method name as
arguments alongside parameters and you need to return result or raise exception.

For an example see the next section.


The complete example
--------------------

.. literalinclude:: ../example_device.py
