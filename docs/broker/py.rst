Running SHV RPC Broker as part of the Python application
========================================================

It is also possible to run SHV Broker directly in Python code as part of your
Asyncio loop. The configuration can be created directly in the code without
having to write TOML file through :class:`shv.broker.RpcBrokerConfig` but to
understand it please read the previous section describing the TOML file format
configuration. You can also create your custom configuration based on the
:class:`shv.broker.RpcBrokerConfigABC` which might be in some cases easier.

The configuration then can be used to initialize :class:`shv.broker.RpcBroker`.
To run the broker you have to await :meth:`shv.broker.RpcBroker.start_serving`.

It is also possible to extend the broker implementation to add custom nodes.
To do so you need to extend :class:`shv.broker.RpcBroker` and include extension
of :class:`shv.broker.RpcBroker.Client`,
:class:`shv.broker.RpcBroker.LoginClient`, and
:class:`shv.broker.RpcBroker.ConnectClient`. The minimal viable overload is:

.. code-block:: python

   from shv.broker import RpcBroker

   class MyBroker(RpcBroker):

       class Client(RpcBroker.Client):
           pass  # Feel free extend this client as you would for SHV device

       class LoginClient(RpcBroker.LoginClient, MyBroker.Client):
          pass  # To inject extended client into login clients.

       class ConnectClient(RpcBroker.LoginClient, MyBroker.Client):
          pass  # To inject extended client into connecting clients.
