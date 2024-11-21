"""Class that provides an easier way to define regular methods and signals."""

from __future__ import annotations

import asyncio
import collections
import collections.abc
import dataclasses
import typing
import weakref

from .rpcerrors import (
    RpcInvalidParamError,
    RpcMethodCallExceptionError,
    RpcUserIDRequiredError,
)
from .rpcmethod import RpcMethodAccess, RpcMethodDesc, RpcMethodFlags
from .shvbase import SHVBase
from .value import SHVType


class SHVMethods(SHVBase):
    """SHV RPC methods and signals implementation helper.

    The regular way to implement methods in :class:`SHVBase` is by defining
    :meth:`SHVBase._ls`, :meth:`SHVBase._dir`, and :meth:`SHVBase._method_call`
    methods. That provides ability to implement discoverability as well as
    method implementation in various dynamic ways. But in real world
    applications it is common that we just want to define custom methods and
    having to implement these methods can be error prune and unnecessary
    complex. This class instead provides a way to define methods that are
    discovered and their integration is handled automatically.
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
            attr = getattr(self, name)
            match attr:
                case self.Method():
                    self._methods[attr.path][attr.desc.name] = attr
                case self.Property():
                    self._methods[attr.path].update(attr._methods())
        super().__init__(*args, **kwargs)

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        if (
            request.path in self._methods
            and request.method in self._methods[request.path]
        ):
            method = self._methods[request.path][request.method]
            if request.access >= method.desc.access:
                if (
                    RpcMethodFlags.USER_ID_REQUIRED in method.desc.flags
                    and request.user_id is None
                ):
                    raise RpcUserIDRequiredError
                return await method._func_call(request)
        return await super()._method_call(request)

    def _ls(self, path: str) -> collections.abc.Iterator[str]:
        """Implement `ls` method for registered methods."""
        yield from super()._ls(path)
        yield from self._ls_node_for_path(path, iter(self._methods))

    def _dir(self, path: str) -> collections.abc.Iterator[RpcMethodDesc]:
        """Provide method description for registered methods."""
        yield from super()._dir(path)
        if path in self._methods:
            for method in self._methods[path].values():
                yield method.desc

    MethodT = collections.abc.Callable[
        [typing.Any, SHVBase.Request],
        SHVType | collections.abc.Coroutine[None, None, SHVType],
    ]
    """
    Type definition for the methods that can be used with decorator
    :meth:`SHVMethods.method`.
    """

    @dataclasses.dataclass(frozen=True)
    class Method:
        """The definition of the RPC Method.

        This allows you to define methods as attributes of the object and such
        methods are automatically discovered and used.
        """

        path: str
        """The SHV path this method is associated with."""
        desc: RpcMethodDesc
        """Method description.

        This defines method name, acceess level as well as other options that
        are considered on method call request.
        """
        func: SHVMethods.MethodT
        """Python method providing the implementation."""
        _bound: weakref.ReferenceType[SHVMethods] | None = None
        """The object this method is bound to."""

        def __get__(
            self, instance: SHVMethods, owner: object
        ) -> collections.abc.Callable:
            """Object method bounding."""
            return dataclasses.replace(self, _bound=weakref.ref(instance))

        async def __call__(
            self,
            signal: str | None = None,
            value: SHVType = None,
            access: RpcMethodAccess = RpcMethodAccess.READ,
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
            await shvmethods._signal(
                self.path, signal, self.desc.name, value, access, user_id
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
        cls, path: str, desc: RpcMethodDesc
    ) -> collections.abc.Callable[[MethodT], SHVMethods.Method]:
        """Decorate method to turn it to :class:`SHVMethods.Method`.

        :param path: SHV path this method is associated with.
        :param desc: Method description.
        """
        return lambda func: cls.Method(path, desc, func)

    GetMethodT = collections.abc.Callable[
        [typing.Any, int | None],
        SHVType | collections.abc.Coroutine[None, None, SHVType],
    ]
    """
    Type definition for the methods that can be used with decorator
    :meth:`SHVMethods.property`.
    """
    SetMethodT = collections.abc.Callable[
        [typing.Any, SHVType, str | None],
        collections.abc.Coroutine[None, None, None] | None,
    ]
    """
    Type definition for the methods that can be used with decorator
    :meth:`SHVMethods.Property.setter`.
    """

    @dataclasses.dataclass
    class Property:
        """The definition of the RPC Property node.

        This allows you to define methods as attributes of the object and such
        methods are automatically discovered and used.

        The preferred way to use this is through :meth:`property`.
        """

        path: str
        """The SHV path this property is associated with."""
        tp: str
        """Type description for this property."""
        access: RpcMethodAccess
        """Minimal access level required for method `get`."""
        func: SHVMethods.GetMethodT
        """Python method providing the implementation for `get` method."""
        signal: bool | str
        """If property has signal and optionally its name.

        `chng` is used if set to `True`. `False` is for not signalized property.
        """
        access_set: RpcMethodAccess = RpcMethodAccess.WRITE
        """Minimal access level required for method `set`."""
        func_set: SHVMethods.SetMethodT | None = None
        """Python method providing the implementation for `set` method."""
        _bound: weakref.ReferenceType[SHVMethods] | None = None
        """The object this `get` and `set` methods are bound to."""

        @typing.overload
        def setter(
            self, access: RpcMethodAccess
        ) -> collections.abc.Callable[[SHVMethods.SetMethodT], SHVMethods.Property]: ...

        @typing.overload
        def setter(self, access: SHVMethods.SetMethodT) -> SHVMethods.Property: ...

        def setter(
            self,
            access: RpcMethodAccess | SHVMethods.SetMethodT = RpcMethodAccess.WRITE,
        ) -> (
            SHVMethods.Property
            | collections.abc.Callable[[SHVMethods.SetMethodT], SHVMethods.Property]
        ):
            """Decorate to define a setter for the SHV RPC property.

            This allows you to set setter. Its usage should be consistend with
            standard :meth:`property.setter`, but if you are using type checking
            tools such as mypy it will trigger `no-redef` rule. You might be
            tempted to just name setter method differently to silence it but
            that would actually define two different property classes. The first
            class without setter would be later overwritten by the new one and
            thus technically this would not be an issue but still it is not
            correct. Thus the suggested way of applying this decorator is with
            `no-redef` type check ignore::

                @SHVMethods.property("prop")
                def prop(self, oldness: int | None) -> SHVType:
                    return self.prop


                @prop.setter  # type: ignore[no-redef]
                def prop(self, param: SHVType, user_id: str | None) -> None:
                    self.prop = param

            :param access: Access level required for `set` method.
            """
            if isinstance(access, RpcMethodAccess):
                return lambda func: dataclasses.replace(
                    self, func_set=func, access_set=access
                )
            return dataclasses.replace(self, func_set=access)

        def __get__(
            self, instance: SHVMethods, owner: object
        ) -> collections.abc.Callable:
            """Object method bounding."""
            return dataclasses.replace(self, _bound=weakref.ref(instance))

        async def __call__(
            self,
            value: SHVType = None,
            access: RpcMethodAccess = RpcMethodAccess.READ,
            user_id: str | None = None,
        ) -> None:
            """External call is used to send signal."""
            shvmethods = self._bound() if self._bound is not None else None
            if shvmethods is None:
                raise UnboundLocalError
            if not self.signal:
                raise NotImplementedError("Method doesn't have any signals")
            await shvmethods._signal(
                self.path,
                "chng" if isinstance(self.signal, bool) else self.signal,
                "get",
                value,
                self.access,
            )

        def _methods(self) -> dict[str, SHVMethods.Method]:
            """Get methods for property implementation."""
            res = {
                "get": SHVMethods.Method(
                    self.path,
                    RpcMethodDesc.getter(
                        result=self.tp, access=self.access, signal=self.signal
                    ),
                    self.__get,
                    self._bound,
                ),
            }
            if self.func_set is not None:
                res["set"] = SHVMethods.Method(
                    self.path,
                    RpcMethodDesc.setter(param=self.tp, access=self.access_set),
                    self.__set,
                    self._bound,
                )
            return res

        def __get(
            self, obj: object, request: SHVBase.Request
        ) -> SHVType | collections.abc.Coroutine[None, None, SHVType]:
            if request.param is not None and not isinstance(request.param, int):
                raise RpcInvalidParamError("Only Int or Null allowed")
            return self.func(obj, request.param)

        def __set(
            self, obj: object, request: SHVBase.Request
        ) -> SHVType | collections.abc.Coroutine[None, None, None]:
            if self.func_set is None:
                # In general this should not happen because we do not register
                # set method as being present in _methods.
                raise RpcMethodCallExceptionError("Set not defined but called")
            return self.func_set(obj, request.param, request.user_id)

    @classmethod
    def property(
        cls,
        path: str,
        tp: str = "Any",
        access: RpcMethodAccess = RpcMethodAccess.READ,
        signal: bool | str = False,
    ) -> collections.abc.Callable[[GetMethodT], SHVMethods.Property]:
        """Decorate method to turn it to :class:`SHVMethods.Property`.

        :param path: SHV path for this property.
        :param tp: Type description provided by this property.
        :param access: Minimal access level required for `get` method.
        :param signal: If property has signal associated with it and optionally
          its name. `chng` is used if `True` is provided and `False` (the]
          default) is used for no signal at all.
        """
        return lambda func: cls.Property(path, tp, access, func, signal)
