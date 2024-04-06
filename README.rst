============================================
Pure Python implementation of Silicon Heaven
============================================
.. image:: https://gitlab.com/silicon-heaven/pyshv/-/raw/master/docs/_static/logo.svg
   :align: right
   :height: 128px

The implementation of serialized and deserializer for CPON and Chainpack as well
as implementation of `Silicon Heaven RPC
<https://silicon-heaven.github.io/shv-doc/>`__.

* `📃 Sources <https://gitlab.com/silicon-heaven/pyshv>`__
* `⁉️ Issue tracker <https://gitlab.com/silicon-heaven/pyshv/-/issues>`__
* `📕 Documentation <https://silicon-heaven.gitlab.io/pyshv/>`__


Installation
------------

The installation can be done with package manager ``pip``.

.. code-block:: console

   $ pip install pyshv


Running tests
-------------

This project contains tests in directory ``tests``.

Tests require `SHV applications <https://github.com/silicon-heaven/shvapp>`__.

To run tests you have to use **pytest**. To run all tests just run it in the top
level directory of the project. See the `pytest documentation
<https://docs.pytest.org/>`__ for more info.


Documentation
-------------

The documentation is stored in `docs` directory. You can build the latest
version from the source code using:

.. code-block:: console

    $ sphinx-build -b html docs docs-html
