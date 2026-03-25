RPC Type hints
==============

.. automodule:: shv.rpctypes
.. autodata:: shv.rpctypes.SHVTypeBitfieldCompatible
.. autodata:: shv.rpctypes.RpcTypeBitfieldCompatible

Predefined types
----------------

.. autodata:: shv.rpctypes.rpctype_any
.. autodata:: shv.rpctypes.rpctype_blob
.. autodata:: shv.rpctypes.rpctype_bool
.. autodata:: shv.rpctypes.rpctype_decimal
.. autodata:: shv.rpctypes.rpctype_double
.. autodata:: shv.rpctypes.rpctype_imap
.. autodata:: shv.rpctypes.rpctype_integer
.. autodata:: shv.rpctypes.rpctype_list
.. autodata:: shv.rpctypes.rpctype_map
.. autodata:: shv.rpctypes.rpctype_null
.. autodata:: shv.rpctypes.rpctype_string
.. autodata:: shv.rpctypes.rpctype_unsigned

.. autodata:: shv.rpctypes.rpctype_clientinfo
.. autodata:: shv.rpctypes.rpctype_datetime
.. autodata:: shv.rpctypes.rpctype_dir
.. autodata:: shv.rpctypes.rpctype_exchange_p
.. autodata:: shv.rpctypes.rpctype_exchange_r
.. autodata:: shv.rpctypes.rpctype_exchange_v
.. autodata:: shv.rpctypes.rpctype_getlog_p
.. autodata:: shv.rpctypes.rpctype_getlog_r
.. autodata:: shv.rpctypes.rpctype_history_records
.. autodata:: shv.rpctypes.rpctype_stat

Inflating / deflating
---------------------

Type hints also support additional conversion between human-readable types and
more encoded ones. This is provided by :meth:`RpcType.inflate` and
:meth:`RpcType.deflate` methods. The following table ilustrates two
representations for different types:

+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| RPC Type     | Deflated (standard) representation                    | Inflated representation                               | Note                                                                                                                                               |
+==============+=======================================================+=======================================================+====================================================================================================================================================+
| Null         | :data:`None`                                          | :data:`None`                                          | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Bool         | :class:`bool` / :class:`shv.SHVBool`                  | :class:`bool` / :class:`shv.SHVBool`                  | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Integer      | :class:`int` / :class:`shv.SHVInt`                    | :class:`int` / :class:`shv.SHVInt`                    | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Enum         | :class:`int` / :class:`shv.SHVInt`                    | :class:`str` / :class:`shv.SHVStr`                    | The ``KEY`` is used for the string value                                                                                                           |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Double       | :class:`float` / :class:`shv.SHVFloat`                | :class:`float` / :class:`shv.SHVFloat`                | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Decimal      | :class:`decimal.Decimal` / :class:`shv.SHVDecimal`    | :class:`decimal.Decimal` / :class:`shv.SHVDecimal`    | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| String       | :class:`str` / :class:`shv.SHVStr`                    | :class:`str` / :class:`shv.SHVStr`                    | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| DateTime     | :class:`datetime.datetime` / :class:`shv.SHVDatetime` | :class:`datetime.datetime` / :class:`shv.SHVDatetime` | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| List         | :class:`list` / :class:`shv.SHVList`                  | :class:`list` / :class:`shv.SHVList`                  | Items in the list are inflated / deflated by associated type rules                                                                                 |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Tuple        | :class:`list` / :class:`shv.SHVList`                  | :class:`dict` / :class:`shv.SHVMap`                   | The ``KEY`` is used as the key and those with value Null are left out while the rest are inflated / deflated with rules for their associated types |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| IMap         | :class:`dict` / :class:`shv.SHVIMap`                  | :class:`dict` / :class:`shv.SHVIMap`                  | Values in the mapping are inflated / deflated by associated type rules                                                                             |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Struct       | :class:`dict` / :class:`shv.SHVIMap`                  | :class:`dict` / :class:`shv.SHVMap`                   | The ``KEY`` is used as replacement for integer key and values are inflated / deflated with rules for their associated types                        |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Map          | :class:`dict` / :class:`shv.SHVMap`                   | :class:`dict` / :class:`shv.SHVMap`                   | Values in the mapping are inflated / deflated by associated type rules                                                                             |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| KeyStruct    | :class:`dict` / :class:`shv.SHVMap`                   | :class:`dict` / :class:`shv.SHVMap`                   | Values in the mapping are inflated / deflated by their associated types rules                                                                      |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Bitfield     | :class:`int` / :class:`shv.SHVInt`                    | :class:`dict` / :class:`shv.SHVMap`                   | Integer is broken up according to the encoding rules and ``KEY`` is used as key for associated decoded items according to the associated types     |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| One of types | :class:`shv.SHVType`                                  | :class:`shv.SHVType`                                  | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Any type     | :class:`shv.SHVType`                                  | :class:`shv.SHVType`                                  | No modification                                                                                                                                    |
+--------------+-------------------------------------------------------+-------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
