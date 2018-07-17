
# Ribosome example: Django project

This repo is example of configured Ribosome release process for
Django project.


## Prerequisites

Install [pyenv](https://github.com/pyenv/pyenv):
packages needed to build Python by [this guide](https://askubuntu.com/a/865644)
and then use [pyenv-installer](https://github.com/pyenv/pyenv-installer#installation--update--uninstallation).

Ensure that pyenv shims come first at PATH.
Place these lines

    export PATH="~/.pyenv/bin:$PATH"
    eval "$(pyenv init -)"
    eval "$(pyenv virtualenv-init -)"

as last ones in `.bashrc` for interactive sessions **and**
also in `.bash_profile` for non-interactive sessions.

Install Python 3.6.5: `pyenv install 3.6.5`.

Install [Pipenv](https://github.com/pypa/pipenv)
into 3.6.5 distribution: `pip install pipenv`.


## Getting started

Setup runtime and build environment:

    $ pyenv local 3.6.5
    $ make devsetup

Setup Django:

    $ pipenv run ./manage.py migrate

Start main Django application:

    $ make run
