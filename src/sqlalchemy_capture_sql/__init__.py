"""
Usage: Example using factory-boy classes
Python 3.7 tested and developed.

with with:

    with CaptureSqlStatements(engine_cloud) as capture_stmts:
        cpm = FactoryModel.create()
    capture_stmts.pp(short=True)

standard style:

    capture_stmts = CaptureSqlStatements(engine_cloud)
    cpm = FactoryModel.create()
    capture_stmts.finish()
    capture_stmts.pp(short=True)

TODO: provide some better examples with plain old sql-s w/wo ORM 

"""
import logging
from typing import List, Any, Dict, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
from collections import Counter

try:
    from sqlalchemy import event
except ImportError as ex:
    raise Exception(f"This package requires some SQLAlchemy preinstalled (pip install sqlalchemy?). Error: {ex}")

# ============================================================
# ============================================================
# ============================================================

@dataclass
class SqlStatement:
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
        assert diff.days==0
        self.duration = diff.seconds + round(diff.microseconds / 1_000_000.0, 2)

    def pp_short(self):
        # do 80 znakova
        out = []
        out.append("%.2f" % (self.duration))
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
class CaptureSqlStatements:

    engine: Any # TODO: typing - sqlalchemy engine
    statements: List[SqlStatement] = field(default_factory=list)
    started : datetime = field(init=False, default_factory=datetime.now)
    finished : Optional[datetime] = field(init=False, default=None)
    decorated_fn : Callable = field(init=False)

    def __post_init__(self):
        # https://docs.sqlalchemy.org/en/13/orm/session_events.html - nema listano, već ovdje (našao u source-u da se zovu)
        # https://docs.sqlalchemy.org/en/13/core/events.html?highlight=before_cursor_execute#sqlalchemy.events.ConnectionEvents.before_cursor_execute
        self.decorated_fn = event.listens_for(self.engine, 'before_cursor_execute')\
                                             (self.capture_sa_statement_listener)

    def __enter__(self):
        return self
      
    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.finish()

    def capture_sa_statement_listener(self, conn, cursor, statement, parameters, context, executemany):
        assert not self.finished
        now = datetime.now()
        if self.statements:
            self.statements[-1].set_tst_next(now)

        self.statements.append(
            SqlStatement(
                statement = statement,
                parameters = parameters,
                tst_started = now,
                executemany=executemany,
                # context
            )
        )

    def finish(self):
        assert not self.finished
        event.remove(self.engine, 'before_cursor_execute', self.decorated_fn)
        self.finished = datetime.now()
        if self.statements:
            self.statements[-1].set_tst_next(self.finished)

    def count(self) -> int:
        return len(self.statements)

    def get_counter(self, name) -> Counter:
        stats = self.get_stats()
        return stats[name]

    def get_stats(self) -> Dict[str, Counter]:
        if not hasattr(self, "_by_type"):
            self._by_type = Counter()
            self._by_table = Counter()
            self._by_type_and_table = Counter()
            for nr, stmt in enumerate(self.statements, 1):
                self._by_type.update([stmt.sql_type])
                self._by_table.update([stmt.first_table])
                self._by_type_and_table.update([f"{stmt.sql_type} {stmt.first_table}"])
        return {"by_type":          self._by_type,
                "by_table":         self._by_table,
                "by_type_and_table":self._by_type_and_table}

    def pp_counter(self, name, top=20):
        counter = self.get_counter(name)
        max_len = max([len(key) for key, _ in counter.most_common(top)])
        fmt = "%%-%ds %%3d" % (max_len+3,)
        return "\n    ".join([fmt % (key, cnt) for key, cnt in counter.most_common(top)])

    def pp(self, short=False):
        if self.statements:
            print(f"== NOTE: duration measures time between 2 captures, it is not actual DB execution time.")
            print(f"== Totally captured {self.count()} statement(s):")
            for nr, stmt in enumerate(self.statements, 1):
                print("%3d. %s" % (nr, stmt.pp_short() if short else stmt))
            print("-- By sql command:")
            print(f"    {self.pp_counter('by_type')}")
            print("-- By table (top 20):")
            print(f"    {self.pp_counter('by_table')}")
            print("-- By sql command + table (top 20):")
            print(f"    {self.pp_counter('by_type_and_table')}")
        else:
            print("No sql statements captured")

    @staticmethod
    def enable_sqlalchemy_debug_stmts():
        logging.basicConfig()
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO) 



