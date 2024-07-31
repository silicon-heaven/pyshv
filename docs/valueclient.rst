Client communication in SHV
===========================

The most basic operation on SHV network is calling methods and reading some
values. Dedicated class is provided for this purpose in form of
:class:`shv.ValueClient`. Note that you can also use :class:`shv.SimpleClient`
directly if you want to just call some methods and don't care about properties
value caching.


Connecting to the broker
------------------------

The first step is to connect client to the SHV broker. For that you need to know
where broker is running and have some sort of access as a user. If you do not
have any broker running then you can use SHV broker configuration intended for
testing of this project. Run the following command in the pySHV source
directory): ``python3 -m shv.broker -c tests/broker/config.toml``.

You need to call function ``ValueClient.connect``
(:func:`shv.SimpleClient.connect`). It will provide you with
:class:`shv.ValueClient` (:class:`shv.SimpleClient`) instance that is connected
and logged in to the SHV broker.

>>> client = await shv.ValueClient.connect("tcp://admin@localhost?password=admin!123")


Discovering SHV tree
--------------------

Once you are connected you can discover tree of nodes and its associated
methods. There is :func:`shv.SimpleClient.ls` method for this purpose available.
Methods associated with some node can be listed with
:func:`shv.SimpleClient.dir`. There are also methods
:func:`shv.SimpleClient.ls_has_child` and :func:`shv.SimpleClient.dir_exists`
for respective node and method existence validation.

This is all you need to iterate over the whole SHV tree of the SHV broker.

>>> await client.ls("")
['.broker']

>>> await client.dir("")
[RpcMethodDesc(name='dir'), RpcMethodDesc(name='ls')]


Calling methods
---------------

Now when you know about available methods (or if know in advance without having
to call ``dir``) you can call any of them using :func:`shv.SimpleBase.call`.

>>> await client.call(".app", "name")
'pyshvbroker'

The method call can result in SHV error that is propagated as Python exception.
To differentiate between errors in your code and errors produced by SHV you can
filter for :class:`shv.RpcError` base class as all SHV errors are based on it.

>>> await client.call("nosuch", "foo")
shv.rpcerrors.RpcMethodCallExceptionError: ("method: foo path: nosuch what: Method: 'foo' on path 'nosuch' doesn't exist", <RpcErrorCode.METHOD_CALL_EXCEPTION: 8>)


Reading and writing values
--------------------------

Some nodes have value associated with them. To receive it they provide common
``get`` method and optionally to change it they provide ``set`` method. You can
call these methods directly or use simple wrappers
:func:`shv.ValueClient.prop_get` and :func:`shv.ValueClient.prop_set`.

To actually demonstrate this we need some device that actually has property
nodes. One of such devices is our example device so feel free to connect it
to your broker and try with it (``python3 example_device.py``).

>>> await client.prop_get("test/device/track/1")
[0]

>>> await client.prop_set("test/device/track/1", [1])
True
>>> await client.prop_get("test/device/track/1")
[1]


Subscribing for changes
-----------------------

The primary functionality of :class:`shv.ValueClient` is to ease access to the
property values. It is not efficient to always call
:func:`shv.ValueClient.prop_get` but we could use old value if we would know
that there was no change in the meantime. SHV RPC solves this by devices
signaling their new value. That way we do not have to ask for new value every
time but we still have it as soon as possible. This of course could get pretty
noisy once there would be multiple devices connected to the SHV broker and we
are never interested in all value changes. Because of that SHV broker filters
all signals unless we explicitly ask for them with
:func:`shv.SimpleClient.subscribe` that expects `Resource Identifier
<https://silicon-heaven.github.io/shv-doc/rpcri.html>`__ to be provided.

:class:`shv.ValueClient` caches subscribed values and you can quickly access
them using subscribe operator (that is Python operator `[]`).

>>> await client.subscribe("test/device/track/**:*:*")))
>>> await client.get_snapshot("test/device/track/**:*:*")))
>>> client["test/device/track/1"]))
[0]
>>> await client.prop_set("test/device/track/1", [1])))
>>> client["test/device/track/1"]))
[1]

In this example we changed value by ourself but
:func:`shv.ValueClient.prop_set` does not in default interact with cache and new
value is rather returned because signal was emitted by device (feel free to
change the value with some separate script or application).

The method :func:`shv.ValueClient.get_snapshot` is called to initialize our
cache. Note that :class:`KeyError` is raised if path is not in cache as we can't
know if it is not there due to not being initialized yet or because there is no
such node.

>>> await client.subscribe("test/device/track/**:*:*")))
>>> client["test/device/track/1"]))
KeyError: 'test/device/track/1'
