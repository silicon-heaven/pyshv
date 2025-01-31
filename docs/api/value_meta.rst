SHV Meta abstraction
====================

The standard types in the

SHV Meta
--------

.. autoclass:: shv.SHVMeta

.. autofunction:: shv.shvmeta
.. autofunction:: shv.shvmeta_eq

SHV Types
---------

These are types based on the :class:`shv.SHVMeta` and this allow storing of the
associated meta attributes to the value of given type.

.. autoclass:: shv.SHVNull
.. autoclass:: shv.SHVBool
.. autoclass:: shv.SHVInt
.. autoclass:: shv.SHVUInt
.. autoclass:: shv.SHVFloat
.. autoclass:: shv.SHVDecimal
.. autoclass:: shv.SHVBytes
.. autoclass:: shv.SHVStr
.. autoclass:: shv.SHVDatetime
.. autoclass:: shv.SHVList
.. autoclass:: shv.SHVMap
.. autoclass:: shv.SHVIMap

SHV specific type checking functions
------------------------------------

Due to the limitation in the type representation in the Python some of the
common type checking conventions must be replaced with the following functions
when working with the data provided from SHV.

.. autofunction:: shv.is_shvnull
.. autofunction:: shv.is_shvbool
.. autofunction:: shv.is_shvlist
.. autofunction:: shv.is_shvmap
.. autofunction:: shv.is_shvimap
.. autofunction:: shv.is_shvtype


Other utilities
---------------

.. autofunction:: shv.decimal_rexp
