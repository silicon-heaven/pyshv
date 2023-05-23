SHV RPC concepts
================

The core of the Silicon Heaven RPC protocol is described in Wiki for
`Qt library <https://github.com/silicon-heaven/libshv/wiki/ChainPack-RPC#rpc>`_
that provides reference implementation.

Silicon Heaven has open ended design that can be tweaked and expanded on due to
its lack of clear boundaries, for that reason this Python implementation
provides this document that is destiled minimal reference of the SHV concepts.

Messages in the network
-----------------------

There are three types of messages used in the Silicon Heaven RPC communication.

:Requests:
    Message used to call some method. Such messages is required to have some
    request ID, method name and optionally some parameters and client IDs and
    SHV path. The other side needs to respond. Parameters can be any valid SHV
    data.
:Responses:
    Message sent by side that received some request. This message has to have
    request ID and response but it can't have method name. It also needs to have
    client IDs if they were present in the request message. The response is any
    valid SHV data.
:Signals:
    Message sent without prior request and thus without request ID. It needs to
    specify method name. It also can contain parameters with any valid SHV data
    and SHV path.

Request ID can be any unique number assigned by side that sends request
initially. It is used to pair up requests with their responses. The common
approach is to just use request message counter as request ID.

Mentioned client IDs are related to the broker and unless you are implementing a
broker you need to know only that they are additional identifiers for the
message alongside the request ID to pair requests with their responses and thus
should be always included in the response message if they were present in the
request.

The SHV path is used to select exact node of method in the SHV tree. The SHV
tree is discussed in the next section.

SHV RPC network design
----------------------

Silicon Heaven RPC is point to point protocol. There are always only two sides
in the communication.  Broadcast is not utilized.

Messages are transmitted between two sides while both sides can send requests.

The bigger networks are constructed using brokers. Broker supports multiple
client connections in parallel and provides exchange of messages between them.
The broker design is discussed in the next section.

It is a good practice to always connect sides through broker and never directly.
That is because broker is the only one that needs to manage multiple connections
in parallel in such case. Clients are only connected to the broker.

Clients can be simple dummy clients that only call some methods and listen for
responses and signals but there are also clients that expose methods and nodes.
We call these clients "devices". Device has tree of nodes where every node can
have multiple methods associated with it. This tree can be discovered through
method ``ls`` that needs to be implemented on every node. Methods associated
with some node can be discovered with ``dir`` method that also has to be
implemented on every node.

Device's tree needs to be accessible to clients through SHV broker and this is
archived by attaching it somewhere in the broker's tree. This operation is
called mounting and you need to specify mount point (node in the SHV broker
tree) when connecting device to the SHV broker. Thanks to this client can
communicate with multiple devices in parallel as well as device can be used by
multiple clients.


SHV RPC Broker
--------------

.. error::
    Not yet implemented in Python.
