============================================
Pure Python implementation of Silicon Heaven
============================================

The implementation of serialized and deserializer for CPON and Chainpack as well
as implementation of `Silicon Heaven RPC
<https://github.com/silicon-heaven/libshv/wiki/ChainPack-RPC#rpc>`__.

* `📃 Sources <https://gitlab.com/elektroline-predator/pyshv>`__
* `⁉️ Issue tracker <https://gitlab.com/elektroline-predator/pyshv/-/issues>`__
* `📕 Documentation <https://elektroline-predator.gitlab.io/pyshv/>`__


Installation
------------

The installation can be done with package manager `pip`.

    pip install .


Running tests
-------------

This project contains tests in directory tests.

To run tests you have to use **pytest**. To run all tests just run it in the top
level directory of the project. See the `pytest documentation
<https://docs.pytest.org/>`__ for more info.


Documentation
-------------

The documentation is available in `docs` directory and build version is
available on https://elektroline-predator.gitlab.io/python-shvtree/. You can
also build the latest version from the source code using:

    sphinx-build -b html docs docs-html
