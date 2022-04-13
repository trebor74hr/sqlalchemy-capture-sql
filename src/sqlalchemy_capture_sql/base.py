"""
TODO: provide some better examples with plain old sql-s w/wo ORM 

"""
import logging
import sqlite3

import enum
from typing import List, Any, Dict, Optional, Callable, Tuple
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

# ------------------------------------------------------------

@dataclass
class Stat:
    key: str
    cnt: int
    duration: float
    statement: Optional[SqlStatement] = None

# ------------------------------------------------------------

class StatName(str, enum.Enum):
    BY_TYPE           = "by_type"
    BY_TABLE          = "by_table"
    BY_TYPE_AND_TABLE = "by_type_and_table"

# ------------------------------------------------------------

TOP_DEFAULT = 20
TOP_DEFAULT_SLOWEST = 5
TAB = " " * 4

# ------------------------------------------------------------

@dataclass
class CaptureSqlStatements:

    engine: Any # TODO: typing - sqlalchemy engine
    statements: List[SqlStatement] = field(default_factory=list)
    started : datetime = field(init=False, default_factory=datetime.now)
    finished : Optional[datetime] = field(init=False, default=None)
    decorated_fn : Callable = field(init=False)
    connection : sqlite3.Connection = field(init=False)

    AGG_FIELDS = (
            "cnt", 
            "duration",
            )
    FMT_MAP = {
            "cnt": "%3d", 
            "duration" : "%7.3f s",
            }

    STATS_NAME_MAP = {
            StatName.BY_TYPE           : "sql_type",
            StatName.BY_TABLE          : "first_table",
            StatName.BY_TYPE_AND_TABLE : "sql_type, first_table",
            }


    def __post_init__(self):
        # https://docs.sqlalchemy.org/en/13/orm/session_events.html - nema listano, već ovdje (našao u source-u da se zovu)
        # https://docs.sqlalchemy.org/en/13/core/events.html?highlight=before_cursor_execute#sqlalchemy.events.ConnectionEvents.before_cursor_execute
        self.decorated_fn = event.listens_for(self.engine, 'before_cursor_execute')\
                                             (self.capture_sa_statement_listener)
        self.connection = sqlite3.connect(":memory:")
        self._cur = self.connection.cursor()
        self._cur.execute("create table sql_statement(id int primary key, duration float, first_table varchar, sql_type varchar)")
        self.connection.commit()


    def __del__(self):
        if hasattr(self, "_cur"):
            try:
                self._cur.close()
            except:
                pass

        if hasattr(self, "_con"):
            try:
                self.connection.close()
            except:
                pass

        return self

    # ------------------------------------------------------------
    # Capture logic implemenntation 
    # ------------------------------------------------------------

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
            self.connection.commit()

    # ---------------------------------------------------------------------
    # Stats methods - returning aggregated or top records as list or dict
    # ---------------------------------------------------------------------

    def count(self) -> int:
        return len(self.statements)

    def _get_max_key_len(self, stat_list:List[Stat], min_length=15) -> int:
        return max([min_length, *[len(st.key) for st in stat_list]])

    def get_slowest(self, top:int=TOP_DEFAULT_SLOWEST) -> List[Stat]:
        " this one fills Stat.statement with original SqlStatement object "
        if not self.finished:
            raise Exception("Call finish() first.")

        self._cur.execute(f"select id, sql_type, first_table, duration from sql_statement order by duration desc limit {top}")
        stat_list = []
        for row in self._cur.fetchall():
            row_id, sql_type, first_table, duration = row
            key = f"{sql_type} {first_table}"
            stmt = self.get_statement_by_row_id(row_id)
            stat_list.append(Stat(key, 1, duration, stmt))
        return stat_list

    def get_statement_by_row_id(self, row_id:int) -> SqlStatement:
        if row_id <1 or row_id > len(self.statements):
            raise Exception(f"Row id {row_id} out of range, valid range is: [1, {len(self.statements)}]")
        return self.statements[row_id-1]

    def get_counts(self, name:StatName) -> Dict[str, int]:
        return {st.key: st.cnt for st in self.get_stats(name)}


    def get_stats(self, name: StatName, top:int=TOP_DEFAULT) -> Tuple[int, List[Stat]]:
        if not self.finished:
            # duration is not calculated
            raise Exception("Call finish() first.")

        if name not in self.STATS_NAME_MAP:
            raise Exception(f"Name {name} is not valid, valid are: {name_map.keys()}")

        group_by = self.STATS_NAME_MAP[name]

        self._cur.execute(f"select count(*) cnt, sum(duration) dur, {group_by} from sql_statement group by {group_by} order by sum(duration) desc, count(*) desc limit {top}")

        stat_list = []
        for row in self._cur.fetchall():
            cnt, duration, *keys = row
            key = " ".join(map(str, keys))
            stat_list.append(Stat(key, cnt, duration))
        return stat_list

    # ----------------------------------------------------------------------
    # Report methods - using stats method produce report as single string
    # ----------------------------------------------------------------------

    def report_slowest(self, verbose=False) -> str:
        slowest_stat_list = self.get_slowest(top=5)
        max_key_len = self._get_max_key_len(slowest_stat_list)
        fmt = "%%3d. %%-%ds %s %s %%s" % (max_key_len, self.FMT_MAP["cnt"], self.FMT_MAP["duration"])
        out = []
        for nr, stat in enumerate(slowest_stat_list,1):
            out.append(fmt % (nr, stat.key, stat.cnt, stat.duration, stat.statement.stmt_repr if not verbose else stat.statement))
        return f"\n{TAB}".join(out)

    def report_counter(self, name: StatName, top:int=TOP_DEFAULT) -> str:
        return self.report_stats(name, fields=["cnt"], top=top)

    def report_stats(self, name: StatName, top:int=TOP_DEFAULT, fields:List[str]=AGG_FIELDS) -> str:
        stat_list = self.get_stats(name)
        max_key_len = self._get_max_key_len(stat_list)
        fmt = "%%-%ds " % (max_key_len,) + " ".join([self.FMT_MAP[fld] for fld in fields])
        return f"\n{TAB}".join([fmt % (st.key, *[getattr(st, fld) for fld in fields]) for st in stat_list])

    # ----------------------------------------------------------------------
    # Pretty-print method - full report to std. out or custom print function
    # ----------------------------------------------------------------------

    def pp(self, verbose:bool=False, print_cmd:Callable=print):
        if self.statements:
            separator_line = "=" * 60
            top = TOP_DEFAULT
            print_cmd(separator_line)
            print_cmd(f"== NOTE: duration measures time between 2 captures, it is not actual DB execution time.")
            total = f"== Totally captured {self.count()} statement(s) in {self.duration} s"
            print_cmd(total+":")
            for nr, stmt in enumerate(self.statements, 1):
                print_cmd("%3d. %s" % (nr, stmt.report_short() if not verbose else stmt))
            print_cmd(separator_line)
            print_cmd(f"== Slowest (top {TOP_DEFAULT_SLOWEST}):")
            print_cmd(f"{TAB}{self.report_slowest(verbose=verbose)}")
            print_cmd(separator_line)
            print_cmd(f"== By sql command (top {top}):")
            print_cmd(f"{TAB}{self.report_stats('by_type')}")
            print_cmd(separator_line)
            print_cmd(f"== By table (top {top}):")
            print_cmd(f"{TAB}{self.report_stats('by_table')}")
            print_cmd(separator_line)
            print_cmd(f"== By sql command + table (top {top}):")
            print_cmd(f"{TAB}{self.report_stats('by_type_and_table')}")
            print_cmd(separator_line)
            print_cmd(total)
        else:
            print_cmd("No sql statements captured")

    # ------------------------------------------------------------
    # Utility functions
    # ------------------------------------------------------------

    @staticmethod
    def sqlalchemy_log_statements_enable():
        " enable sqlalchemy sql commands logging. One can use SqlAlchemy.Engine(... echo=True) too "
        # logging.basicConfig()
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO) 

    @staticmethod
    def sqlalchemy_log_statements_disable():
        # logging.basicConfig()
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING) 

