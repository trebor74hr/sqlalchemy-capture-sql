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

With python's **with** statement:

    from sqlalchemy_capture_sql import CaptureSqlStatements

    with CaptureSqlStatements(sqlalchemy_engine) as capture_stmts:

        # put here calls to functions that issue sqlalchemy commands that
        # produce some sql statements execution, for example factory-boy:
        cpm = FactoryModel.create()

        # call to .finish() automatically done on with ctx exit
    capture_stmts.pp(short=True)

standard style:

    capture_stmts = CaptureSqlStatements(sqlalchemy_engine)

    # put here calls to functions that issue sqlalchemy commands that
    # produce some sql statements execution, for example factory-boy:
    cpm = FactoryModel.create()

    # in this case .finish() needs to be called to stop capturing
    capture_stmts.finish()

    capture_stmts.pp(short=True)


Example:

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

    user1 = User(name='ed', fullname='Ed Jones', nickname='edsnickname')

    session.add(user1)
    session.commit()

    with CaptureSqlStatements(engine) as capture_stmts:
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


Call to pp():

    capture_stmts.pp()

produces:

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
