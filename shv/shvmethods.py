"""Class that provides an easier way to define regular methods and signals."""

from __future__ import annotations

import asyncio
import collections
import collections.abc
import dataclasses
import typing
import weakref

from .rpcaccess import RpcAccess
from .rpcdir import RpcDir
from .rpcerrors import RpcInvalidParamError, RpcUserIDRequiredError
from .rpcmessage import RpcMessage
from .shvbase import SHVBase
from .value import SHVType

SHVMethodT: typing.TypeAlias = collections.abc.Callable[
    [typing.Any, SHVBase.Request],
    SHVType | collections.abc.Coroutine[None, None, SHVType],
]
SHVGetMethodT: typing.TypeAlias = collections.abc.Callable[
    [typing.Any, int | None],
    collections.abc.Coroutine[None, None, SHVType] | SHVType,
]
SHVSetMethodT: typing.TypeAlias = collections.abc.Callable[
    [typing.Any, SHVType, str | None],
    collections.abc.Coroutine[None, None, None] | None,
]


class SHVMethods(SHVBase):
    """SHV RPC methods and signals implementation helper.

    The regular way to implement methods in :class:`shv.SHVBase` is by defining
    :meth:`shv.SHVBase._ls`, :meth:`shv.SHVBase._dir`, and
    :meth:`shv.SHVBase._method_call` methods. That provides ability to implement
    discoverability as well as method implementation in various dynamic ways.
    But in real world applications it is common that we just want to define
    custom methods and having to implement these methods can be error-prone and
    unnecessary complex. This class instead provides a way to define methods
    that are discovered and their integration is handled automatically.
    """

    def __init__(
        self,
        *args: typing.Any,  # noqa ANN401
        **kwargs: typing.Any,  # noqa ANN401
    ) -> None:
        self._methods: dict[str, dict[str, SHVMethods.Method]] = (
            collections.defaultdict(dict)
        )
        for name in dir(self):
            if isinstance(attr := getattr(self, name, None), self.Method):
                if attr.desc.name in self._methods[attr.path]:
                    raise ValueError(
                        f"Method already defined {attr.path}:{attr.desc.name}"
                    )
                self._methods[attr.path][attr.desc.name] = attr
        super().__init__(*args, **kwargs)

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        if (
            request.path in self._methods
            and request.method in self._methods[request.path]
        ):
            method = self._methods[request.path][request.method]
            if request.access >= method.desc.access:
                if (
                    RpcDir.Flag.USER_ID_REQUIRED in method.desc.flags
                    and request.user_id is None
                ):
                    raise RpcUserIDRequiredError
                return await method._func_call(request)
        return await super()._method_call(request)

    def _ls(self, path: str) -> collections.abc.Iterator[str]:
        """Implement `ls` method for registered methods."""
        yield from super()._ls(path)
        yield from self._ls_node_for_path(path, iter(self._methods))

    def _dir(self, path: str) -> collections.abc.Iterator[RpcDir]:
        """Provide method description for registered methods."""
        yield from super()._dir(path)
        if path in self._methods:
            for method in self._methods[path].values():
                yield method.desc

    @dataclasses.dataclass(frozen=True)
    class Method:
        """The definition of the RPC Method.

        This allows you to define methods as attributes of the object and such
        methods are automatically discovered and used. Note that the discovery
        is performed on object initialization.

        The following is provided and thus not required to be performed in the
        method itself:

        - Check if SHV path and method name matches as otherwise this method
          would not be called.
        - Verification of the access level.
        - Verifies if user's ID is required (based on the
          :attr:`shv.RpcDir.flags`) and sends
          :class:`shv.RpcUserIDRequiredError` error.

        What application has to do on its own:

        - Implement the method behavior and return the method result.
        - Validate parameter and raise :class:`shv.RpcInvalidParamError` for
          invalid values.
        - Explicitly send signals.
        """

        path: str
        """The SHV path this method is associated with."""
        desc: RpcDir
        """Method description.

        This defines method name, acceess level as well as other options that
        are considered on method call request.
        """
        func: SHVMethodT
        """Python method providing the implementation."""

        _bound: weakref.ReferenceType[SHVMethods] | None = None

        def __get__(self, instance: SHVMethods, owner: object) -> SHVMethods.Method:
            """Object method bounding."""
            return dataclasses.replace(self, _bound=weakref.ref(instance))

        async def signal(
            self,
            value: SHVType = None,
            signal: str | None = None,
            access: RpcAccess = RpcAccess.READ,
            user_id: str | None = None,
        ) -> None:
            """External call is used to send signals."""
            shvmethods = self._bound() if self._bound is not None else None
            if shvmethods is None:
                raise UnboundLocalError
            if signal is None:
                if not self.desc.signals:
                    raise NotImplementedError("Method doesn't have any signals")
                signal = next(iter(self.desc.signals.keys()))
            elif signal not in self.desc.signals:
                raise ValueError(f"Invalid signal name: {signal}")
            await shvmethods._send(
                RpcMessage.signal(
                    self.path, signal, self.desc.name, value, access, user_id
                )
            )

        async def _func_call(self, request: SHVBase.Request) -> SHVType:
            shvmethods = self._bound() if self._bound is not None else None
            if shvmethods is None:
                raise UnboundLocalError
            res = self.func(shvmethods, request)
            if asyncio.iscoroutine(res):
                res = await res
            return res

    @classmethod
    def method(
        cls, path: str, desc: RpcDir
    ) -> collections.abc.Callable[[SHVMethodT], SHVMethods.Method]:
        """Decorate method to turn it to :class:`shv.SHVMethods.Method`.

        :param path: SHV path this method is associated with.
        :param desc: Method description.
        """
        return lambda func: cls.Method(path, desc, func)

    @classmethod
    def property(
        cls,
        path: str,
        tp: str = "Any",
        access: RpcAccess = RpcAccess.READ,
        signal: bool | str = False,
    ) -> collections.abc.Callable[[SHVGetMethodT], SHVMethods.Method]:
        """Decorate method to use method as ``get`` property method.

        The properties are common standard ways to organize access to the values
        exposed over SHV. This decorator provides an easier way to implement
        these common methods by validating the parameter.

        The decorated function is called in wrapper that on top of the
        :class:`Method` handling also verifies the parameter.

        :param path: SHV path for this property.
        :param tp: Type description provided by this property.
        :param access: Minimal access level required for `get` method.
        :param signal: If property has signal associated with it and optionally
          its name. `chng` is used if `True` is provided and `False` (the]
          default) is used for no signal at all.
        """

        def wrapper(func: SHVGetMethodT) -> SHVMethods.Method:
            def substitut(
                obj: SHVMethods, request: SHVBase.Request
            ) -> collections.abc.Coroutine[None, None, SHVType] | SHVType:
                if request.param is not None and not isinstance(request.param, int):
                    raise RpcInvalidParamError("Only Int or Null allowed")
                return func(obj, request.param)

            return cls.Method(
                path,
                RpcDir.getter(result=tp, access=access, signal=signal),
                substitut,
            )

        return wrapper

    @classmethod
    def property_setter(
        cls,
        getter: Method,
        access: RpcAccess = RpcAccess.WRITE,
    ) -> collections.abc.Callable[[SHVSetMethodT], SHVMethods.Method]:
        """Decorate method to make it set method for the property node.

        This is a companion decorator to the :meth:`property` that allows
        addition of the ``set`` method to the property node.

        :param getter: The reference to the ``get`` method.
        :param access: Minimal access level required for ``set`` method.
        """
        if getter.desc.name != "get":
            raise ValueError("Can be used only on method get")

        def wrapper(func: SHVSetMethodT) -> SHVMethods.Method:
            def substitut(
                obj: SHVMethods, request: SHVBase.Request
            ) -> collections.abc.Coroutine[None, None, None] | None:
                return func(obj, request.param, request.user_id)

            return cls.Method(
                getter.path,
                RpcDir.setter(param=getter.desc.result, access=access),
                substitut,
            )

        return wrapper
