Project Template Python
=======================

This is description of your project. Do NOT forget to modify it together with
title of this file, project dependencies and other parts of this file which
would require the change.

* `📃 Sources <https://gitlab.elektroline.cz/emb/template/python>`__
* `⁉️ Issue tracker <https://gitlab.elektroline.cz/emb/template/python/-/issues>`__


Running tests
-------------

This project contains basic tests in directory tests; see the dependencies in
the `pyproject.toml` file.

To run tests you have to use **pytest**. To run all tests just run it in the top
level directory of the project::

    pytest

See the `pytest documentation <https://docs.pytest.org/>`__ for more info.


Documentation
-------------

The documentation is available in ``docs`` directory. You can build it using::

    sphinx-build -b html docs docs-html
