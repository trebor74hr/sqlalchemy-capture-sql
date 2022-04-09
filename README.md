# sqlalchemy-capture-sql

A small library that enables capturing SQLAlchemy SQL statements / queries.

Django has [django.db.connection.queries](https://docs.djangoproject.com/en/4.0/faq/models/#how-can-i-see-the-raw-sql-queries-django-is-running)
connection property that enables user to display executed raw SQL queries
(DEBUG mode only).
Sometimes in debugging or unit testing this can serve the purpose to check and
control nr.  and type of sql statements executed for monitored case. 

This library provides simple class that enables similar behaviour, but for
[SQLAlchemy](https://www.sqlalchemy.org/). Each SQL statement is captured along
with passed parameters. 

## How it works
Internally it uses 
[event.listens_for(engine, 'before_cursor_execute'](https://docs.sqlalchemy.org/en/13/core/events.html?highlight=before_cursor_execute#sqlalchemy.events.ConnectionEvents.before_cursor_execute)
event handler, e.g.:

    @event.listens_for(engine, 'before_cursor_execute')
    def capture_sa_statement_listener(...)

It simply collects all sql statements sent to event listeer by SQLAlchemy (sent
just before execution) and statements are collected in CaptureSqlStatements
instance until .finish() method is called (or with ctx is exited).

Additionally it provides time measurement (see REMARKS), stats and formatting
functions, see Examples.

## REMARKS

Some remarks:

 * There is some "heuristic" duration measurement, i.e. class measures time
   between 2 captures, it is not actual DB execution time.

 * Capturing type of command and table name is very simple and one should not
   rely on it.


Tested and developed on Python 3.7+SQLAlchemy 1.3, but I assume it should work
on later and probably some previous versions.

## Installation
As usual:

    pip install sqlalchemy-capture-sql

## Example usage

Some very simple examples using [factory-boy classes](https://factoryboy.readthedocs.io/en/stable/index.html), **more to come**.

with **with** python statement:

    from sqlalchemy_capture_sql import CaptureSqlStatements

    with CaptureSqlStatements(engine_cloud) as capture_stmts:

        # put here calls to functions that issue sqlalchemy commands that
        # produce some sql statements execution, for example factory-boy:
        cpm = FactoryModel.create()

        # call to .finish() automatically done on with ctx exit
    capture_stmts.pp(short=True)

standard style:

    capture_stmts = CaptureSqlStatements(engine_cloud)

    # put here calls to functions that issue sqlalchemy commands that
    # produce some sql statements execution, for example factory-boy:
    cpm = FactoryModel.create()

    # in this case .finish() needs to be called to stop capturing
    capture_stmts.finish()

    capture_stmts.pp(short=True)


Both cases produces same result, it could look like this:

    == NOTE: duration measures time between 2 captures, it is not actual DB execution time.

    == Totally captured 5 statement(s):

      1. 0.00 SELECT FROM person ORDER BY person.id DESC
      2. 0.00 INSERT INTO company_access (alive, allow_empty_cashbag,
         <- 'True+True+False+True+True+False+False+False+False+False+False+False+T
      3. 0.00 SELECT FROM person  WHERE person.id = %(param_1)s
         <- '4'
      4. 0.00 SELECT FROM company_access  WHERE company...
         <- '3'
      5. 0.01 INSERT INTO company_person (packing_model_id, company_access_i
         <- '4+3'

    -- By sql command:
        SELECT  3
        INSERT  2

    -- By table (top 20):
        PERSON          2
        COMPANY_ACCESS  2
        COMPANY_PERSON  1

    -- By sql command + table (top 20):
        SELECT PERSON          2
        INSERT COMPANY_ACCESS  1
        SELECT COMPANY_ACCESS  1
        INSERT COMPANY_PERSON  1

One can iterate all statements:

    for statement in capture_stmts:
        print(statement.statement)
        print(statement.tst_started)
        print(statement.duration)    # BEWARE: not actual DB execution time, 
                                               Rounded on 2 decimal places.
        print(statement.stmt_repr)   # Dropped list of columns from SELECT
        print(statement.parameters)
        print(statement.executemany) # bool
        print(statement.sql_type)    # BEWARE: do not rely on this
        print(statement.first_table) # BEWARE: do not rely on this
 
<!--


test markdown:

    pip install markdown
    python -m markdown README.md  > r.html && open r.html

markdown syntax: 

    https://www.markdownguide.org/basic-syntax/

Deployment:
    reference:
        https://towardsdatascience.com/5-simple-steps-to-package-and-publish-your-python-code-to-pypi-d9f5c43f9d4

Initially:

    pip install wheel
    py -m pip install --upgrade build

    pip install twine # installs a bunch of thing
    # bleach-5.0.0 commonmark-0.9.1 docutils-0.18.1 keyring-23.5.0 pkginfo-1.8.2
    # readme-renderer-34.0 requests-toolbelt-0.9.1 rich-12.2.0 twine-4.0.0
    # webencodings-0.5.1

    rm -Rf dist/* 

    # build and deploy
    py -m build

    # deploy on test pypi
    py -m twine upload --repository testpypi dist/* --verbose

    # check on https://test.pypi.org/project/sqlalchemy-capture-sql/0.1.0/

    # if ok then install on pypi 
    py -m twine upload dist/* --verbose

    # check on: https://pypi.org/project/sqlalchemy-capture-sql/0.1.0/

    git commit && git push

Upgrade version:

    rm -Rf dist/* 

    # increase version number in setup.cfg
    # if not done, then upload to pypi will report:
    #    400 File already exists. See https://pypi.org/help/#file-name-reuse
    #    for more information.

    py -m twine upload --repository testpypi dist/* --verbose

    # check on https://test.pypi.org/project/sqlalchemy-capture-sql/0.1.0/

    # if ok then upload on pypi
    py -m twine upload dist/* --verbose


    # if ok then install on pypi
    py -m twine upload --skip-existing dist/*

    # check on: https://pypi.org/project/sqlalchemy-capture-sql/0.1.0/

    git commit && git push

Shortcut:

    rm -Rf dist/* && py -m build && py -m twine upload dist/* --verbose

test:
    create venv or init existing one
    pip uninstall sqlalchemy-capture-sql
    pip install sqlalchemy-capture-sql==0.1.1

    python -c"from sqlalchemy_capture_sql import CaptureSqlStatements"

-->
