API reference for SHV values
============================

The standard Python types are used always when it is possible but there is a
concept of meta data assigned to the value in SHV. To ensure that it is
supported it was required to introduce additional types. These types are all
based on :class:`shv.SHVMeta`.

.. autoclass:: shv.SHVMeta
.. autofunction:: shv.shvmeta
.. autofunction:: shv.shvmeta_eq
.. autoclass:: shv.SHVNull
.. autofunction:: shv.is_shvnull
.. autoclass:: shv.SHVBool
.. autofunction:: shv.is_shvbool
.. autoclass:: shv.SHVInt
.. autoclass:: shv.SHVUInt
.. autoclass:: shv.SHVFloat
.. autoclass:: shv.SHVDecimal
.. autoclass:: shv.SHVStr
.. autoclass:: shv.SHVBytes
.. autoclass:: shv.SHVDatetime
.. autoclass:: shv.SHVList
.. autoclass:: shv.SHVDict
.. autofunction:: shv.is_shvmap
.. autofunction:: shv.is_shvimap
.. autoclass:: shv.SHVType
.. autoclass:: shv.SHVMetaType
