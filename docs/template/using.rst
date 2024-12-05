How to use the Project Template Python
======================================

*Project Template Python* works as a synchronization mechanism between
Python-based projects. A project using this template should keep the
``template`` remote in the Git repository and merge the changes from the
``template/master`` branch when the Project Template Python is updated.

Sections below describe how to use the Project Template Python when
creating new project, introducing the template for the existing project,
or merging the updates of the template.


Creating new project with Project Template Python
-------------------------------------------------

1. Create new repository

   When creating new repository in GitLab, do **not** initialize
   repository with README.

   Clone new repository:

   .. code-block:: shell

    git clone git@gitlab.elektroline.cz:path/to/newproj.git

   Or initialize new repository locally and later add ``origin``
   remote:

   .. code-block:: shell

    mkdir newproj
    cd newproj
    git init --initial-branch=master
    git remote add origin git@gitlab.elektroline.cz:path/to/newproj.git

2. Create the first commit in the new repository

   Add README file:

   .. code-block:: shell

    cat > README.rst <<EOF
    This is a description for the new project. Make sure to describe
    here the project before commiting.
    EOF
    git add README.rst
    git commit -m 'Add readme'

   And push the commit to the ``origin`` remote::

    git push -u origin master

3. Add Git remote for the Project Template Python

   Create ``dev`` branch for prototyping::

    git checkout -b dev

   Add ``template`` remote and merge the template into the prototype
   development branch::

    git remote add template https://gitlab.elektroline.cz/emb/template/python.git
    git fetch template
    git merge --allow-unrelated-histories template/master

   When merging the template into the main development branch, there
   will probably be merge conflicts. When creating new project, merge
   conflicts are expected to be only in the README.

   Resolve merge conflict in README and complete the merge -- make the
   README look like it should.

4. Rename template to fit the project

   There is a ``rename.sh`` script that changes the *one line project
   description*, GitLab links, ``project-name``, and ``package_name`` in
   all necessary places all over the template::

    ./rename.sh

   After running the script, do not forget to further update README with
   more elaborate description and other appropriate information.

5. Cleanup

   Remove any template specific files. These are files such as
   ``rename.sh`` script::

    rm rename.sh

   or this documentation::

    rm -r docs/template

   Do not forget to write your own documentation!

6. Commit all changes as part of merge commit

   Add new package to be tracked in the Git history::

    git add new_package_name/

   Finally, the last step is to stage all changes you made and modify
   merge commit created at the beginning. This can be done by:

   .. code-block:: shell

    git commit --all --amend -C HEAD


Using Project Template Python for existing project
--------------------------------------------------

1. Add Git remote for the Project Template Python

   ::

    git remote add template https://gitlab.elektroline.cz/emb/template/python.git
    git fetch template

2. Merge the template into the development branch

   ::

    git merge --allow-unrelated-histories template/master

   When merging the template into the main or prototype development
   branch, there will probably be merge conflicts. Contrary to *creating
   new project*, there will be more merge conflicts then just in README.

   Resolve merge conflict and complete the merge.


Merge updates of the Project Template Python
--------------------------------------------

Merging updates of the Project Template Python into the main or
prototype development branch consist basically of resolving merge
conflicts after issuing the merge command::

    git fetch template
    git merge template/master

Resolve merge conflict and complete the merge.
