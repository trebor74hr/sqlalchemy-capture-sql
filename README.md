# sqlalchemy-capture-sql

A small library that enables capturing SQLAlchemy SQL statements / queries.

Django has [django.db.connection.queries](https://docs.djangoproject.com/en/4.0/faq/models/#how-can-i-see-the-raw-sql-queries-django-is-running)
connection property that enables user to display executed raw SQL queries
(DEBUG mode only).
Sometimes in debugging or unit testing this can serve the purpose to check and
control nr.  and type of sql statements executed for monitored case. 

This library provides simple class that enables similar behaviour, but for
[SQLAlchemy](https://www.sqlalchemy.org/). Each SQL statement is captured along
with passed parameters. Internally it uses 
[event.listens_for(engine, 'before_cursor_execute'](https://docs.sqlalchemy.org/en/13/core/events.html?highlight=before_cursor_execute#sqlalchemy.events.ConnectionEvents.before_cursor_execute)
event handler, e.g.:

    @event.listens_for(engine, 'before_cursor_execute')
    def capture_sa_statement_listener(...)

REMARKS: 

 * There is some "heuristic" duration measurement, i.e. class measures time
   between 2 captures, it is not actual DB execution time.

 * Capturing type of command and table name is very simple and one should not
   rely on it.


Tested and developed on Python 3.7+SQLAlchemy 1.3, but I assume it should work
on later and probably some previous versions.

Some very simple examples using factory-boy classes, more to come.

with **with** python statement:

    with CaptureSqlStatements(engine_cloud) as capture_stmts:
        # put here any calls that issue sqlalchemy commands that produce some
        # sql statements execution.
        cpm = FactoryModel.create()
        # no .finish() needed
    capture_stmts.pp(short=True)

standard style:

    capture_stmts = CaptureSqlStatements(engine_cloud)
    # put here any calls that issue sqlalchemy commands that produce some
    # sql statements execution.
    cpm = FactoryModel.create()
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
        SELECT      3
        INSERT      2

    -- By table (top 20):
        PERSON                    2
        COMPANY_ACCESS      2
        COMPANY_PERSON            1

    -- By sql command + table (top 20):
        SELECT PERSON                    2
        INSERT COMPANY_ACCESS      1
        SELECT COMPANY_ACCESS      1
        INSERT COMPANY_PERSON            1

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
pip install markdown
python -m markdown README.md  > r.html && open r.html
-->
