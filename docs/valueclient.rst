Reading values in SHV
=====================

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
testing of this project: ``shvbroker --config-dir tests/shvbroker-etc``.

You need to call function ``ValueClient.connect``
(:func:`shv.SimpleClient.connect`). It will provide you with
:class:`shv.ValueClient` instance that is connected and logged in to the SHV
broker.

>>> client = await shv.ValueClient.connect("localhost", user="admin", password="admin!123", login_type=shv.SimpleClient.LoginType.PLAIN)


Discovering SHV tree
--------------------

Once you are connected you can discover tree of nodes and its associated
methods. There is :func:`shv.SimpleClient.ls` method for this purpose available.
Methods associated with some node can be listed with
:func:`shv.SimpleClient.dir`. There are also methods
:func:`shv.SimpleClient.ls_with_children` and
:func:`shv.SimpleClient.dir_details` with additional info provided.

This is all you need to iterate over the whole SHV tree of the SHV broker.

>>> await client.ls("")
['.broker']

>>> await client.dir("")
['dir', 'ls']


Calling methods
---------------

Now when you know methods available (or you can know it in advance without
having to call ``dir``) you can call any of them using
:func:`shv.SimpleClient.call`.

>>> await client.call(".broker/app", "echo", "Hello")
'Hello'

The method call can result in SHV error that is propagated as Python exception.
To differentiate between errors in your code and errors produced by SHV you can
filter for :class:`shv.RpcError` base class as all errors are based on it.

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
:func:`shv.ValueClient.prop_get` but we could use old value if we wouldn't do it
every time. SHV RPC solves this by devices signaling their new value. That way
we do not have to ask for new value every time but we still have it as soon as
possible. This of course could get pretty noisy once there would be multiple
devices connected to the SHV broker and we are never interested in all changes.
Because of that SHV broker filters all signals unless we explicitly ask for them
through :func:`shv.SimpleClient.subscribe`. Subscribing is always recursive and
thus signals from child nodes are also propagated. :class:`shv.ValueClient`
caches these values and you can quickly access them using subscribe operator.

>>> await client.subscribe("test/device/track")))
>>> await client.get_snapshot("test/device/track")))
>>> client["test/device/track/1"]))
[0]
>>> await client.prop_set("test/device/track/1", [1])))
>>> client["test/device/track/1"]))
[1]

In this example we changed value by ourself but
:func:`shv.ValueClient.prop_set` does not interact with cache and new value is
rather returned because signal was emitted by device (feel free to change the
value with some separate script or application).

The method :func:`shv.ValueClient.get_snapshot` is called to initialize our
cache. Note that :class:`KeyError` is raised if path is not in cache as we can't
know if it is not there due to not being initialized yet or because there is no
such node.

>>> await client.subscribe("test/device/track")))
>>> client["test/device/track/1"]))
KeyError: 'test/device/track/1'
