# sqlalchemy-capture-sql

sqlalchemy-capture-sql is a library that enables capturing
[SQLAlchemy](https://www.sqlalchemy.org/) SQL statements / queries.
Each SQL statement is captured along with passed parameters and approx.
duration of execution time. It provides reporting and analysis functionalities,
for instance: aggregations by type of sql command, table name, list of slowest
queries and so on.

## Motivation
Django has
[django.db.connection.queries](https://docs.djangoproject.com/en/4.0/faq/models/#how-can-i-see-the-raw-sql-queries-django-is-running)
connection property that enables user to display executed raw SQL queries
(DEBUG mode only).
Sometimes in debugging or unit testing this can serve the purpose to check and
control number and type of sql statements executed for monitored case, along
with allowed duration times. I wanted to create similar functionality for
SQLAlchemy and provide additional statistics and analysis functions. 

## How it works
Internally it uses 
[event.listens_for(engine, 'before_cursor_execute'](https://docs.sqlalchemy.org/en/13/core/events.html?highlight=before_cursor_execute#sqlalchemy.events.ConnectionEvents.before_cursor_execute)
event handler, e.g.:

    @event.listens_for(engine, 'before_cursor_execute')
    def capture_sa_statement_listener(...)

It simply collects all sql statements sent to event listener by SQLAlchemy (sent
just before execution) and statements are collected in CaptureSqlStatements
instance until .finish() method is called (or "with" context is exited).

Additionally it provides time measurement (see REMARKS), stats and formatting
functions, see Examples.

## REMARKS

Some remarks:

 * duration measurement is not actual DB execution time, **system
   measures time between 2 sql statements captures**

 * system tries to detect type of sql command (select, insert, ...) and first
   referenced table/db-object name, but the logic behind is very simple and one
   should not rely on it.

Tested and developed on Python 3.7+SQLAlchemy 1.3, but I assume it should work
on later and probably some previous versions.


## Installation
As usual:

    pip install sqlalchemy-capture-sql

## Usage example

Standard usage is by using python's **with** statement:

    from sqlalchemy_capture_sql import CaptureSqlStatements

    with CaptureSqlStatements(sqlalchemy_engine) as capture_stmts:

        # put here calls to functions that issue sqlalchemy commands that
        # produce some sql statements execution, for example factory-boy:
        cpm = FactoryModel.create()

        # call to .finish() automatically done on with ctx exit
    capture_stmts.pp()

but standard style works too - finish() needs to be called:

    capture_stmts = CaptureSqlStatements(sqlalchemy_engine)

    # put here calls to functions that issue sqlalchemy commands that
    # produce some sql statements execution, for example factory-boy:
    cpm = FactoryModel.create()

    # in this case .finish() needs to be called to stop capturing
    capture_stmts.finish()


Calling pretty print function:

    capture_stmts.pp()

the library will make full report, for instance:

    ============================================================
      1. 0.0020 INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
         <- 'joe+Joe Joey+joey'
      2. 0.0009 SELECT FROM users  WHERE users.id = ?
         <- '2'
      ...
    ============================================================
    == Slowest (top 5):
          1. INSERT USERS             1   0.002 s INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
          2. INSERT USERS             1   0.001 s INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
          ...
    ============================================================
    == By sql command (top 20):
        INSERT               2   0.003 s
        SELECT               4   0.003 s
        UPDATE               1   0.001 s
        DELETE               1   0.001 s
    ============================================================
    == By table (top 20):
        USERS                6   0.007 s
        ...
    ============================================================
    == By sql command + table (top 20):
        INSERT USERS             2   0.003 s
        SELECT USERS             2   0.002 s
        UPDATE USERS             1   0.001 s
        ...

    == Totally captured 8 statement(s) in 0.008866 s

### Working example - a long one

This working example illustrates use of some raw sqls and ORM objects (inspired by
[SqlAlchemy 1.3 tutorial](https://docs.sqlalchemy.org/en/13/orm/tutorial.html)):

    from sqlalchemy_capture_sql import CaptureSqlStatements
    from sqlalchemy import create_engine, text, Column, Integer, String
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker

    Base = declarative_base()

    class User(Base):
        __tablename__ = 'users'

        id = Column(Integer, primary_key=True)
        name = Column(String)
        fullname = Column(String)
        nickname = Column(String)


    engine = create_engine('sqlite:///:memory:', echo=False)
    conn = engine.connect()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    session = Session()

    # This orm operation won't be captured
    user1 = User(name='ed', fullname='Ed Jones', nickname='edsnickname')
    session.add(user1)
    session.commit()

    with CaptureSqlStatements(engine) as capture_stmts:
        # All commands within engine executed in this with block will be captured
        joe = User(name='joe', fullname='Joe Joey', nickname='joey')
        session.add(joe)
        session.commit()

        session.query(User).count()

        # one raw sql
        conn.execute(text("select 'In-capture'")).fetchall()

        joe.nickname = "Jo"
        session.commit()

        session.add(User(name='Wrong', fullname='Wrong', nickname='wrong'))
        session.rollback()

        jack = User(name='Jack', fullname='Jackson', nickname='jackie')
        session.add(jack)
        session.commit()

        session.delete(jack)
        session.commit()

    # This orm operation won't be captured
    session.add(User(name='Mick', fullname='Michael', nickname='mick'))
    assert session.query(User).count(), 3

    assert capture_stmts.get_counts("by_type"), {'INSERT': 2, 'SELECT': 4, 'UPDATE': 1, 'DELETE': 1}
    assert capture_stmts.get_counts("by_table"), {"'IN-CAPTURE'": 1, '(SELECT': 1, 'USERS': 6}
    assert capture_stmts.get_counts("by_type_and_table"), {
        'DELETE USERS': 1,
        'INSERT USERS': 2,
        "SELECT 'IN-CAPTURE'": 1,
        'SELECT (SELECT': 1,
        'SELECT USERS': 2,
        'UPDATE USERS': 1}

    assert [st.stmt_repr for st in capture_stmts.statements], [
        'INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)',
        'SELECT FROM (SELECT users.id AS users_id, users.name AS users_name, '
            'users.fullname AS users_fullname, users.nickname AS users_nickname \n'
            'FROM users) AS anon_1',
        "select 'In-capture'",
        'SELECT FROM users \nWHERE users.id = ?',
        'UPDATE users SET nickname=? WHERE users.id = ?',
        'INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)',
        'SELECT FROM users \nWHERE users.id = ?',
        'DELETE FROM users WHERE users.id = ?']


Call to pretty-print function:

    capture_stmts.pp()

Produces:

    ============================================================
    == NOTE: duration measures time between 2 captures, it is not actual DB execution time.
    == Totally captured 8 statement(s) in 0.008866 s:
      1. 0.0020 INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
         <- 'joe+Joe Joey+joey'
      2. 0.0005 SELECT FROM (SELECT users.id AS users_id, users.name AS users_name, us
      3. 0.0010 select 'In-capture'
      4. 0.0009 SELECT FROM users  WHERE users.id = ?
         <- '2'
      5. 0.0013 UPDATE users SET nickname=? WHERE users.id = ?
         <- 'Jo+2'
      6. 0.0014 INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
         <- 'Jack+Jackson+jackie'
      7. 0.0007 SELECT FROM users  WHERE users.id = ?
         <- '3'
      8. 0.0005 DELETE FROM users WHERE users.id = ?
         <- '3'

    ============================================================
    == Slowest (top 5):
          1. INSERT USERS             1   0.002 s INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
          2. INSERT USERS             1   0.001 s INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
          3. UPDATE USERS             1   0.001 s UPDATE users SET nickname=? WHERE users.id = ?
          4. SELECT 'IN-CAPTURE'      1   0.001 s select 'In-capture'
          5. SELECT USERS             1   0.001 s SELECT FROM users
    WHERE users.id = ?

    ============================================================
    == By sql command (top 20):
        INSERT               2   0.003 s
        SELECT               4   0.003 s
        UPDATE               1   0.001 s
        DELETE               1   0.001 s

    ============================================================
    == By table (top 20):
        USERS                6   0.007 s
        'IN-CAPTURE'         1   0.001 s
        (SELECT              1   0.000 s

    ============================================================
    == By sql command + table (top 20):
        INSERT USERS             2   0.003 s
        SELECT USERS             2   0.002 s
        UPDATE USERS             1   0.001 s
        SELECT 'IN-CAPTURE'      1   0.001 s
        DELETE USERS             1   0.001 s
        SELECT (SELECT           1   0.000 s

    ============================================================
    == Totally captured 8 statement(s) in 0.008866 s


One can iterate all capture statement objects:

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


## Misc

### Other methods

Check also other instance methods of CaptureSqlStatements in order to get some
stats in list/dict objects, for instance:

    count() -> int
    get_counts(name:StatName) -> Dict[str, int]
    get_slowest(top:int=TOP_DEFAULT_SLOWEST) -> List[Stat]
    get_statement_by_row_id(row_id:int) -> SqlStatement
    get_stats(name: StatName, top:int=TOP_DEFAULT) -> Tuple[int, List[Stat]]
    pp(verbose:bool=False, print_cmd:Callable=print)
    report_counter(name: StatName, top:int=TOP_DEFAULT) -> str
    report_slowest(verbose=False) -> str
    report_stats(name: StatName, top:int=TOP_DEFAULT, fields:List[str]=AGG_FIELDS) -> str

### Sqlite3 internal database

Internally library uses
[sqlite3](https://docs.python.org/3/library/sqlite3.html) in memory database to
store basic statement information.  Database is used for statistics,
aggregations and finding slowest queries, but one can use it for further
analysis, e.g.:

    cursor = capture_stmts.connection.cursor()
    cursor.execute(f"select id, sql_type, first_table, duration from sql_statement order by duration desc limit 100")
    for row in cursor.fetchall():
        row_id, sql_type, first_table, duration = row
        stmt = capture_stmts.get_statement_by_row_id(row_id)
        print(f"{sql_type} {first_table} {duration} : {stmt.statement} <- {stmt.parameters}")

### SQLAlchemy statements logging

SQLAlchemy can log sql statements when log on "sqlalchemy.engine" level is set
at least to INFO level:

    import logging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO) 

This functionalitiy also attached to CaptureSqlStatements as static methods in:

    sqlalchemy_log_statements_enable()
    sqlalchemy_log_statements_disable()

Alternative is providing echo=True attribute when creating SqlAlchemy.Engine
with echo attribute, for instance:

    engine = create_engine('sqlite:///...', echo=True)


## Running tests

Do git clone of the repository, go to root folder and run:

    python tests/test_basic.py

To see verbose output - pp() result, run like this:

    VERBOSE=1 python tests/test_basic.py

