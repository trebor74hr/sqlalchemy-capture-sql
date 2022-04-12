"""
TODO: provide some better examples with plain old sql-s w/wo ORM 

"""
import logging
import sqlite3

from typing import List, Any, Dict, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
from collections import Counter

try:
    from sqlalchemy import event
except ImportError as ex:
    raise Exception(f"This package requires some SQLAlchemy preinstalled (pip install sqlalchemy?). Error: {ex}")

def timedelta_to_seconds(diff):
    return diff.days * 24 * 60 * 60 + diff.seconds + diff.microseconds / 1_000_000.0

# ============================================================
# ============================================================
# ============================================================

@dataclass
class SqlStatement:
    idx: int # unique id=1... (index0-1) in final list
    statement: str = field(repr=False)
    # context
    tst_started : datetime = field(repr=False)
    # of the next statement
    tst_next: Optional[datetime] = field(init=False, default=None, repr=False)
    duration: Optional[float] = field(init=False, default=None)
    stmt_repr: str = field(init=False) # representation
    parameters: Any # List|Tuple|Dict[str, Any]
    executemany: bool
    sql_type: str = field(init=False) # Enum?
    first_table: str = field(init=False) # Enum?

    def __post_init__(self):
        # default
        sql = self.statement
        flds = [f.upper() for f in sql.split()[:20]]
        self.sql_type = flds[0]

        if self.sql_type in ("SELECT",):
            from_idx = sql.upper().find("FROM ")
            if from_idx>0:
                self.first_table = sql[from_idx:].split()[1].upper()
                sql = self.sql_type + " " + sql[from_idx:]
            else:
                # give me something, first column
                self.first_table = flds[1]
        elif flds[:2]==["INSERT", "INTO"]:
            self.first_table = flds[2]
        elif flds[:2]==["DELETE", "FROM"]:
            self.first_table = flds[2]
        elif flds[:1]==["UPDATE",]:
            self.first_table = flds[1]
        else:
            self.first_table = "<unknown>"

        self.stmt_repr = sql

    def set_tst_next(self, tst):
        self.tst_next = tst
        diff = (self.tst_next - self.tst_started)
        self.duration = timedelta_to_seconds(diff)

    def report_short(self):
        # do 80 znakova
        out = []
        out.append("%.4f" % (self.duration))
        sql = "%s" % (self.stmt_repr[:70].replace("\n", " "),)
        out.append(sql)

        if isinstance(self.parameters, dict):
            params = self.parameters.values()
        elif isinstance(self.parameters, (list, tuple)):
            params = self.parameters
        else:
            params = [self.parameters.values]
        if params:
            params = "\n     <- " + repr("+".join([str(p) for p in params]))[:70]
            out.append(params)
        return " ".join(out)


@dataclass
class Stat:
    key: str
    cnt: int
    duration: float

# ------------------------------------------------------------
TOP_DEFAULT = 20
# ------------------------------------------------------------

@dataclass
class CaptureSqlStatements:

    engine: Any # TODO: typing - sqlalchemy engine
    statements: List[SqlStatement] = field(default_factory=list)
    started : datetime = field(init=False, default_factory=datetime.now)
    finished : Optional[datetime] = field(init=False, default=None)
    decorated_fn : Callable = field(init=False)

    AGG_FIELDS = ("cnt", "duration")

    def __post_init__(self):
        # https://docs.sqlalchemy.org/en/13/orm/session_events.html - nema listano, već ovdje (našao u source-u da se zovu)
        # https://docs.sqlalchemy.org/en/13/core/events.html?highlight=before_cursor_execute#sqlalchemy.events.ConnectionEvents.before_cursor_execute
        self.decorated_fn = event.listens_for(self.engine, 'before_cursor_execute')\
                                             (self.capture_sa_statement_listener)
        self._con = sqlite3.connect(":memory:")
        self._cur = self._con.cursor()
        self._cur.execute("create table sql_statement(id int primary key, duration float, first_table varchar, sql_type varchar)")
        self._con.commit()


    def __del__(self):
        if hasattr(self, "_cur"):
            try:
                self._cur.close()
            except:
                pass

        if hasattr(self, "_con"):
            try:
                self._con.close()
            except:
                pass

        return self

    def __enter__(self):
        return self
      
    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.finish()

    def __iter__(self):
        for stmt in self.statements:
            yield stmt

    def capture_sa_statement_listener(self, conn, cursor, statement, parameters, context, executemany):
        if self.finished:
            raise Exception("finish() already done, capture not possible any more")
        now = datetime.now()
        if self.statements:
            self.statements[-1].set_tst_next(now)

        stmt = SqlStatement(
                idx = len(self.statements)+1,
                statement = statement,
                parameters = parameters,
                tst_started = now,
                executemany=executemany,
                # context
            )

        self.statements.append(stmt)

    def finish(self):
        if self.finished:
            raise Exception("finish() already called.")

        event.remove(self.engine, 'before_cursor_execute', self.decorated_fn)
        self.finished = datetime.now()
        diff = self.finished - self.started
        self.duration = timedelta_to_seconds(diff)

        if self.statements:
            self.statements[-1].set_tst_next(self.finished)
            # When I have all durations set
            for stmt in self.statements:
                self._cur.execute("insert into sql_statement values (?, ?, ?, ?)",
                                  (stmt.idx, stmt.duration, stmt.first_table, stmt.sql_type))
            self._con.commit()

    def count(self) -> int:
        return len(self.statements)

    def get_stats(self, name, top=TOP_DEFAULT):
        if not self.finished:
            # duration is not calculated
            raise Exception("Call finish() first.")

        name_map = {
            "by_type": "sql_type",
            "by_table": "first_table",
            "by_type_and_table": "sql_type, first_table",
            }
        if name not in name_map:
            raise Exception(f"Name {name} is not valid, valid are: {name_map.keys()}")

        group_by = name_map[name]

        self._cur.execute(f"select count(*) cnt, sum(duration) dur, {group_by} from sql_statement group by {group_by} order by sum(duration) desc, count(*) desc")

        max_key_len = 15
        stats = []
        for row in self._cur.fetchall():
            cnt, duration, *keys = row
            key = " ".join(map(str, keys))
            max_key_len = max([max_key_len, len(key)])
            stats.append(Stat(key, cnt, duration))
        return max_key_len, stats

    def get_counts(self, name):
        return {st.key: st.cnt for st in self.get_stats(name)[1]}

    def report_counter(self, name, top=TOP_DEFAULT):
        return self.report_stats(name, fields=["cnt"], top=top)

    def report_stats(self, name, top=TOP_DEFAULT, fields=AGG_FIELDS):
        fmt_map = {"cnt": "%3d", "duration" : "%7.3f s"}
        max_key_len, stats = self.get_stats(name)
        fmt = "%%-%ds " % (max_key_len+3,) + " ".join([fmt_map[fld] for fld in fields])
        return "\n    ".join([fmt % (st.key, *[getattr(st, fld) for fld in fields]) for st in stats])

    def pp(self, verbose=False, print_cmd=print):
        if self.statements:
            top = TOP_DEFAULT
            print_cmd(f"== NOTE: duration measures time between 2 captures, it is not actual DB execution time.")
            print_cmd(f"== Totally captured {self.count()} statement(s) in {self.duration} s:")
            for nr, stmt in enumerate(self.statements, 1):
                print_cmd("%3d. %s" % (nr, stmt.report_short() if not verbose else stmt))
            print_cmd("-- By sql command:")
            print_cmd(f"    {self.report_stats('by_type')}")
            print_cmd(f"-- By table (top {top}):")
            print_cmd(f"    {self.report_stats('by_table')}")
            print_cmd(f"-- By sql command + table (top {top}):")
            print_cmd(f"    {self.report_stats('by_type_and_table')}")
        else:
            print_cmd("No sql statements captured")

    @staticmethod
    def enable_sqlalchemy_debug_stmts():
        logging.basicConfig()
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO) 




