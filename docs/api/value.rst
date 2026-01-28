SHV values
==========

The standard Python types are used always when it is possible but there is a
concept of meta data assigned to the value in SHV. To ensure that it is
supported it was required to introduce additional types. These types are all
based on :class:`shv.SHVMeta`.

There is also issue in differentiating the SHV's Map and IMap. The native
representation in Python for both is :class:`dict` and thus empty dictionary can
be both IMap as well as Map. As the rule we decided that empty dictionaries are
considered IMap. If you need to pack empty Map you must use :class:`shv.SHVMap`
instead.

+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| SHV Type | Python representation      | Meta type                | Typing hint               | Type checking                                           |
+==========+============================+==========================+===========================+=========================================================+
| Null     | :data:`None`               | :class:`shv.SHVNull`     | :type:`shv.SHVNullType`   | :func:`shv.is_shvnull`                                  |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| Bool     | :class:`bool`              | :class:`shv.SHVBool`     | :type:`shv.SHVBoolType`   | :func:`shv.is_shvbool`                                  |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| Int      | :class:`int`               | :class:`shv.SHVInt`      | :type:`int`               | :func:`isinstance` with type :class:`int`               |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| UInt     | No representation          | :class:`shv.SHVUInt`     | :type:`shv.SHVUInt`       | :func:`isinstance` with type :class:`shv.SHVUInt`       |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| Double   | :class:`float`             | :class:`shv.SHVFloat`    | :type:`float`             | :func:`isinstance` with type :class:`float`             |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| Decimal  | :class:`decimal.Decimal`   | :class:`shv.SHVDecimal`  | :type:`decimal.Decimal`   | :func:`isinstance` with type :class:`decimal.Decimal`   |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| Blob     | :class:`bytes`             | :class:`shv.SHVBytes`    | :type:`bytes`             | :func:`isinstance` with type :class:`bytes`             |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| String   | :class:`str`               | :class:`shv.SHVStr`      | :type:`str`               | :func:`isinstance` with type :class:`str`               |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| DateTime | :class:`datetime.datetime` | :class:`shv.SHVDatetime` | :type:`datetime.datetime` | :func:`isinstance` with type :class:`datetime.datetime` |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| List     | :class:`list`              | :class:`shv.SHVList`     | :type:`shv.SHVListType`   | :func:`shv.is_shvlist`                                  |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| Map      | :class:`dict`              | :class:`shv.SHVMap`      | :type:`shv.SHVMapType`    | :func:`shv.is_shvmap`                                   |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+
| IMap     | :class:`dict`              | :class:`shv.SHVIMap`     | :type:`shv.SHVIMapType`   | :func:`shv.is_shvimap`                                  |
+----------+----------------------------+--------------------------+---------------------------+---------------------------------------------------------+

.. toctree::
   :maxdepth: 2

   value_meta
   value_typehints

   chainpack
   cpon
   cpcommon
