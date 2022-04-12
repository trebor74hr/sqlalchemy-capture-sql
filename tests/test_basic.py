# pytest
import sys, os
import unittest

# setup path dynamically 
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(BASE_DIR)

# next one will report if sqlalchemy is not available
from sqlalchemy_capture_sql import CaptureSqlStatements
from sqlalchemy import create_engine, text, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


Base = declarative_base()


class TestBase(unittest.TestCase):

    def setUp(self):
        self.verbose = bool(os.environ.get("VERBOSE", None))
        self.engine = create_engine('sqlite:///:memory:', echo=self.verbose)
        self.conn = self.engine.connect()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception as ex:
            print("Error: ignored conn.close(): {ex}")

# ------------------------------------------------------------

class TestBasic(TestBase):

    def test_raw_sqls(self):
        result = self.conn.execute(text("select 'Before capture'")).fetchall()
        self.assertEqual(result, [('Before capture',)])

        with CaptureSqlStatements(self.engine) as capture_stmts:
            self.conn.execute(text("select 'In-capture-1'")).fetchall()
            self.conn.execute(text("select 'In-capture-2'")).fetchall()

        self.conn.execute(text("select 'After capture'")).fetchall()

        if self.verbose:
            capture_stmts.pp()
        self.assertEqual(capture_stmts.get_counts("by_type"), {"SELECT" : 2})
        self.assertEqual(
                [st.statement for st in capture_stmts.statements],
                ["select 'In-capture-1'", "select 'In-capture-2'"])

# ------------------------------------------------------------

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    fullname = Column(String)
    nickname = Column(String)


class TestTables(TestBase):

    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)

        self.session = Session()

        self.user1 = User(name='ed', fullname='Ed Jones', nickname='edsnickname')

        self.session.add(self.user1)
        self.session.commit()


    def test_table_data(self):
        self.assertEqual(self.session.query(User).count(), 1)
        with CaptureSqlStatements(self.engine) as capture_stmts:
            joe = User(name='joe', fullname='Joe Joey', nickname='joey')
            self.session.add(joe)
            self.session.commit()

            self.session.query(User).count()

            # one raw sql
            self.conn.execute(text("select 'In-capture'")).fetchall()

            joe.nickname = "Jo"
            self.session.commit()

            self.session.add(User(name='Wrong', fullname='Wrong', nickname='wrong'))
            self.session.rollback()

            jack = User(name='Jack', fullname='Jackson', nickname='jackie')
            self.session.add(jack)
            self.session.commit()

            self.session.delete(jack)
            self.session.commit()

        self.session.add(User(name='Mick', fullname='Michael', nickname='mick'))
        self.assertEqual(self.session.query(User).count(), 3)

        if self.verbose:
            capture_stmts.pp()

        self.assertEqual(
                capture_stmts.get_counts("by_type"), 
                {'INSERT': 2, 'SELECT': 4, 'UPDATE': 1, 'DELETE': 1})
        self.assertEqual(
                capture_stmts.get_counts("by_table"), 
                {"'IN-CAPTURE'": 1, '(SELECT': 1, 'USERS': 6})
        self.assertEqual(
                capture_stmts.get_counts("by_type_and_table"), 
                {'DELETE USERS': 1,
                 'INSERT USERS': 2,
                 "SELECT 'IN-CAPTURE'": 1,
                 'SELECT (SELECT': 1,
                 'SELECT USERS': 2,
                 'UPDATE USERS': 1})

        self.assertEqual(
                [st.stmt_repr for st in capture_stmts.statements],
                ['INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)',
                 'SELECT FROM (SELECT users.id AS users_id, users.name AS users_name, '
                    'users.fullname AS users_fullname, users.nickname AS users_nickname \n'
                    'FROM users) AS anon_1',
                 "select 'In-capture'",
                 'SELECT FROM users \nWHERE users.id = ?',
                 'UPDATE users SET nickname=? WHERE users.id = ?',
                 'INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)',
                 'SELECT FROM users \nWHERE users.id = ?',
                 'DELETE FROM users WHERE users.id = ?']
                )

        def dummy_print(*args, **kwargs):
            pass

        # ------------------------------------------------------------
        # white smoke tests - just call
        # ------------------------------------------------------------
        for name in ("by_type", "by_table", "by_type_and_table"):
            capture_stmts.get_counts(name)
            capture_stmts.report_counter(name)
            capture_stmts.report_stats(name)
            capture_stmts.report_stats(name, fields=["duration"])
            capture_stmts.report_stats(name, fields=["cnt"])

        capture_stmts.report_slowest()

        capture_stmts.pp(verbose=False, print_cmd=dummy_print)
        capture_stmts.pp(verbose=True, print_cmd=dummy_print)

        # pp()
        # == NOTE: duration measures time between 2 captures, it is not actual DB execution time.
        # == Totally captured 8 statement(s) in 0.00775 s:
        #   1. 0.0017 INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
        #      <- 'joe+Joe Joey+joey'
        #   2. 0.0003 SELECT FROM (SELECT users.id AS users_id, users.name AS users_name, us
        #   3. 0.0009 select 'In-capture'
        #   4. 0.0006 SELECT FROM users  WHERE users.id = ?
        #      <- '2'
        #   5. 0.0013 UPDATE users SET nickname=? WHERE users.id = ?
        #      <- 'Jo+2'
        #   6. 0.0014 INSERT INTO users (name, fullname, nickname) VALUES (?, ?, ?)
        #      <- 'Jack+Jackson+jackie'
        #   7. 0.0006 SELECT FROM users  WHERE users.id = ?
        #      <- '3'
        #   8. 0.0004 DELETE FROM users WHERE users.id = ?
        #      <- '3'
        # -- By sql command:
        #     INSERT               2   0.003 s
        #     SELECT               4   0.002 s
        #     UPDATE               1   0.001 s
        #     DELETE               1   0.000 s
        # -- By table (top {top}):
        #     USERS                6   0.006 s
        #     'IN-CAPTURE'         1   0.001 s
        #     (SELECT              1   0.000 s
        # -- By sql command + table (top {top}):
        #     INSERT USERS             2   0.003 s
        #     UPDATE USERS             1   0.001 s
        #     SELECT USERS             2   0.001 s
        #     SELECT 'IN-CAPTURE'      1   0.001 s
        #     DELETE USERS             1   0.000 s
        #     SELECT (SELECT           1   0.000 s

if __name__ == '__main__':
    unittest.main()
