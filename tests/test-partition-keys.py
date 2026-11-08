import sqlite3
import pytest
from collections import OrderedDict


def test_constructor_limit(db, snapshot):
    assert exec(
        db,
        """
        create virtual table v using vec0(
          p1 int partition key,
          p2 int partition key,
          p3 int partition key,
          p4 int partition key,
          p5 int partition key,
          v float[1]
        )
      """,
    ) == snapshot(name="max 4 partition keys")


def test_constraint_values(db):
    # vec0 checks partition key constraints in its own query of the chunks it
    # stores, so it has to keep the rows SQLite keeps for the declared types:
    # those of `plain`, and those of SQLite's own scan of `v`.
    db.execute(
        "create virtual table v using vec0(p integer partition key, s text partition key, a float[1], chunk_size=8)"
    )
    db.execute("create table plain(id integer primary key, p integer, s text)")
    for row in [(1, 5, "a"), (2, 6, "A"), (3, 5, "b  "), (4, 7, "5")]:
        db.execute("insert into v(rowid, p, s, a) values (?, ?, ?, '[1]')", row)
        db.execute("insert into plain values (?, ?, ?)", row)

    def rowids(sql, parameters):
        return sorted(row[0] for row in db.execute(sql, parameters))

    mismatches = []
    for where in [
        "p = ?", "p != ?", "p > ?", "p <= ?",
        "s = ?", "s != ?", "s < ?",
        "s = ? collate nocase", "s != ? collate nocase", "s >= ? collate nocase", "s = ? collate rtrim",
    ]:
        for value in [None, 5, 5.0, 5.5, "5", " 5", "a", "A", "b", b"\x05"]:
            want = rowids(f"select id from plain where {where}", [value])
            for sql in [
                f"select rowid from v where a match '[1]' and k = 10 and {where}",
                f"select rowid from v where {where}",
            ]:
                if rowids(sql, [value]) != want:
                    mismatches.append((sql, value, rowids(sql, [value]), want))
    assert mismatches == []


def test_normal(db, snapshot):
    db.execute(
        "create virtual table v using vec0(p1 int partition key, a float[1], chunk_size=8)"
    )

    db.execute("insert into v(rowid, p1, a) values (1, 100, X'11223344')")
    assert vec0_shadow_table_contents(db, "v") == snapshot(name="1 row")
    db.execute("insert into v(rowid, p1, a) values (2, 100, X'44556677')")
    assert vec0_shadow_table_contents(db, "v") == snapshot(name="2 rows, same parition")
    db.execute("insert into v(rowid, p1, a) values (3, 200, X'8899aabb')")
    assert vec0_shadow_table_contents(db, "v") == snapshot(name="3 rows, 2 partitions")


def test_types(db, snapshot):
    db.execute(
        "create virtual table v using vec0(p1 int partition key, a float[1], chunk_size=8)"
    )

    # EVIDENCE-OF: V11454_28292
    assert exec(
        db, "insert into v(p1, a) values(?, ?)", ["not int", b"\x11\x22\x33\x44"]
    ) == snapshot(name="1. raises type error")

    assert vec0_shadow_table_contents(db, "v") == snapshot(name="2. empty DB")

    # but allow NULLs
    assert exec(
        db, "insert into v(p1, a) values(?, ?)", [None, b"\x11\x22\x33\x44"]
    ) == snapshot(name="3. allow nulls")

    assert vec0_shadow_table_contents(db, "v") == snapshot(
        name="4. show NULL partition key"
    )


def test_updates(db, snapshot):
    db.execute(
        "create virtual table v using vec0(p text partition key, a float[1], chunk_size=8)"
    )

    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [1, "a", b"\x11\x11\x11\x11"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [2, "a", b"\x22\x22\x22\x22"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [3, "a", b"\x33\x33\x33\x33"]
    )

    assert exec(db, "select * from v") == snapshot(name="1. Initial dataset")
    assert exec(db, "update v set p = ? where rowid = ?", ["new", 1]) == snapshot(
        name="2. update #1"
    )


def test_vacuum(db, snapshot):
    db.execute(
        "create virtual table v using vec0(p text partition key, a float[1])"
    )

    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [1, "a", b"\x11\x11\x11\x11"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [2, "a", b"\x22\x22\x22\x22"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [3, "a", b"\x33\x33\x33\x33"]
    )

    exec(db, "delete from v where 1 = 1")
    prev_page_count = exec(db, "pragma page_count")["rows"][0]["page_count"]

    db.execute("insert into v(v) values ('optimize')")
    db.commit()
    db.execute("vacuum")

    cur_page_count = exec(db, "pragma page_count")["rows"][0]["page_count"]
    assert cur_page_count < prev_page_count


class Row:
    def __init__(self):
        pass

    def __repr__(self) -> str:
        return repr()


def exec(db, sql, parameters=[]):
    try:
        rows = db.execute(sql, parameters).fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        return {
            "error": e.__class__.__name__,
            "message": str(e),
        }
    a = []
    for row in rows:
        o = OrderedDict()
        for k in row.keys():
            o[k] = row[k]
        a.append(o)
    result = OrderedDict()
    result["sql"] = sql
    result["rows"] = a
    return result


def vec0_shadow_table_contents(db, v):
    shadow_tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like ? order by 1", [f"{v}_%"]
        ).fetchall()
    ]
    o = {}
    for shadow_table in shadow_tables:
        if shadow_table.endswith("_info"):
            continue
        o[shadow_table] = exec(db, f"select * from {shadow_table}")
    return o


@pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 38, 0),
    reason="partition IN lists need sqlite3_vtab_in(), SQLite 3.38",
)
def test_in_list(db):
    # `part in (...)` used to reach xFilter once per listed value, each call
    # returning its own k nearest, so a query asked for k rows and got k per
    # value. The whole list is now one constraint on the chunks query.
    # https://github.com/asg017/sqlite-vec/issues/142
    db.execute(
        "create virtual table v using vec0(part integer partition key, s text partition key, a float[1], chunk_size=8)"
    )
    for rowid in range(1, 25):
        db.execute(
            "insert into v(rowid, part, s, a) values (?, ?, ?, ?)",
            [rowid, rowid % 4, "abc"[rowid % 3], f"[{rowid}]"],
        )

    def rowids(sql, parameters=[]):
        return [row[0] for row in db.execute(sql, parameters)]

    knn = "select rowid from v where a match '[0]' and k = 5 and "
    assert rowids(knn + "part in (1, 2)") == [1, 2, 5, 6, 9]
    assert rowids(knn + "part in (?, ?)", [2, 1]) == [1, 2, 5, 6, 9]
    assert rowids(knn + "part in (select 1 union all select 2)") == [1, 2, 5, 6, 9]
    assert rowids(knn + "part in (3)") == [3, 7, 11, 15, 19]
    # the list keeps the column's affinity, as `part = '1'` does
    assert rowids(knn + "part in ('1', '2')") == [1, 2, 5, 6, 9]
    assert rowids(knn + "part in (1.0, 2)") == [1, 2, 5, 6, 9]
    assert rowids(knn + "part in (1.5, 2)") == [2, 6, 10, 14, 18]
    # nothing listed, or nothing matching, finds nothing
    assert rowids(knn + "part in (select 1 where 0)") == []
    assert rowids(knn + "part in (7, 8)") == []
    # combined with constraints on the other partition key
    assert rowids(knn + "part in (1, 2) and s = 'a'") == [6, 9, 18, 21]
    assert rowids(knn + "part in (1, 2) and s in ('a', 'b')") == [1, 6, 9, 10, 13]
    assert rowids(knn + "part in (1, 2) and s collate nocase in ('A', 'b')") == [1, 6, 9, 10, 13]
    # `x in (...) collate nocase` collates the result of IN, not its
    # comparisons, so SQLite and vec0 both keep the BINARY collation there
    assert rowids(knn + "part in (1, 2) and s in ('A', 'b') collate nocase") == [1, 10, 13, 22]
    assert rowids(knn + "s in ('A', 'B')") == []
    assert rowids(knn + "s collate rtrim in ('a ', 'b')") == [1, 3, 4, 6, 7]
    # the plan handles the list in one xFilter call
    plan = db.execute(
        "explain query plan " + knn + "part in (1, 2)"
    ).fetchone()[3]
    assert plan.endswith("]Ag_")

    # the same rows SQLite keeps, for every listed value type
    db.execute("create table plain(id integer primary key, part integer, s text)")
    db.execute("insert into plain select rowid, part, s from v")
    mismatches = []
    for where in ["part in (?, ?)", "s in (?, ?)", "s collate nocase in (?, ?)", "s in (?, ?) collate nocase", "s collate rtrim in (?, ?)"]:
        for values in [(None, 1), (1, 2.0), ("1", "2"), ("a", "B"), (b"\x01", 1), (5.5, "a")]:
            want = sorted(rowids(f"select id from plain where {where}", values))
            got = sorted(rowids(f"select rowid from v where a match '[0]' and k = 100 and {where}", values))
            if got != want:
                mismatches.append((where, values, got, want))
    assert mismatches == []


def test_update_without_point_lookup(db):
    # An UPDATE whose WHERE clause is not `rowid = ?` runs on a full scan,
    # which used to hand xUpdate the current partition key as if it were a new
    # value, so every such UPDATE failed with "UPDATE on partition key columns
    # are not supported yet". https://github.com/asg017/sqlite-vec/issues/261
    db.execute(
        "create virtual table v using vec0(part integer partition key, tag integer, +note text, a float[1], chunk_size=8)"
    )
    db.execute("create table images(id integer primary key)")
    db.execute("insert into images values (1), (3)")
    for rowid in range(1, 5):
        db.execute(
            "insert into v(rowid, part, tag, note, a) values (?, ?, 0, 'n', ?)",
            [rowid, rowid, f"[{rowid}]"],
        )

    def rows():
        return [tuple(r) for r in db.execute("select rowid, part, tag, note from v order by rowid")]

    db.execute("update v set tag = 1 where tag = 0")
    assert rows() == [(1, 1, 1, "n"), (2, 2, 1, "n"), (3, 3, 1, "n"), (4, 4, 1, "n")]
    db.execute("update v set tag = 2 where part in (select id from images)")
    assert rows() == [(1, 1, 2, "n"), (2, 2, 1, "n"), (3, 3, 2, "n"), (4, 4, 1, "n")]
    db.execute("update v set note = 'x' where exists (select 1 from images where images.id = v.part)")
    assert rows() == [(1, 1, 2, "x"), (2, 2, 1, "n"), (3, 3, 2, "x"), (4, 4, 1, "n")]
    db.execute("update v set tag = 3 from images where v.part = images.id")
    assert rows() == [(1, 1, 3, "x"), (2, 2, 1, "n"), (3, 3, 3, "x"), (4, 4, 1, "n")]
    db.execute("update v set a = '[9]' where tag = 1")
    assert [tuple(r) for r in db.execute("select rowid from v where a match '[9]' and k = 2")] == [(2,), (4,)]
    # through a KNN plan too
    db.execute("update v set tag = 4 where a match '[9]' and k = 2")
    assert rows() == [(1, 1, 3, "x"), (2, 2, 4, "n"), (3, 3, 3, "x"), (4, 4, 4, "n")]
    # the same partition key value is not a change
    db.execute("update v set part = 2 where rowid = 2")
    db.execute("update v set part = part where tag = 4")
    # a real change of the partition key is still refused, on both plans
    for sql in ["update v set part = 9 where rowid = 1", "update v set part = 9 where tag = 3"]:
        with pytest.raises(sqlite3.OperationalError, match="UPDATE on partition key columns are not supported yet"):
            db.execute(sql)
    assert rows() == [(1, 1, 3, "x"), (2, 2, 4, "n"), (3, 3, 3, "x"), (4, 4, 4, "n")]


@pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 38, 0),
    reason="partition IN lists need sqlite3_vtab_in(), SQLite 3.38",
)
def test_in_list_long(db):
    # the list reaches the chunks query as one pointer-bound set, so it is
    # not subject to SQLITE_LIMIT_VARIABLE_NUMBER (32,766 by default)
    db.execute(
        "create virtual table v using vec0(part integer partition key, s text partition key, a float[1], chunk_size=8)"
    )
    for rowid in range(1, 9):
        db.execute("insert into v(rowid, part, s, a) values (?, ?, ?, ?)", [rowid, rowid * 10000, str(rowid), f"[{rowid}]"])
    many = "with recursive n(x) as (select 1 union all select x + 1 from n where x < 50000) select x from n"
    assert [r[0] for r in db.execute(f"select rowid from v where a match '[0]' and k = 3 and part in ({many})")] == [1, 2, 3]
    assert [r[0] for r in db.execute(f"select rowid from v where a match '[0]' and k = 3 and s in ({many})")] == [1, 2, 3]
    assert [r[0] for r in db.execute(f"select rowid from v where a match '[0]' and k = 3 and part in ({many}) and s in ({many})")] == [1, 2, 3]


@pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 38, 0),
    reason="partition IN lists need sqlite3_vtab_in(), SQLite 3.38",
)
def test_in_list_awkward_values(db):
    # the list values are copied and compared in C, so text with embedded NUL
    # bytes keeps its length, very long values do not lengthen the chunks SQL,
    # and a lowered SQL length limit does not matter
    db.execute(
        "create virtual table v using vec0(part integer partition key, s text partition key, a float[1], chunk_size=8)"
    )
    rows = [(1, 1, "a"), (2, 2, "a\x00b"), (3, 3, "A\x00B"), (4, 4, "a\x00b  "), (5, 5, "x" * 4000)]
    for rowid, part, s in rows:
        db.execute("insert into v(rowid, part, s, a) values (?, ?, ?, ?)", [rowid, part, s, f"[{rowid}]"])
    db.execute("create table plain(id integer primary key, part integer, s text)")
    db.executemany("insert into plain values (?, ?, ?)", rows)
    db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 2000)

    def rowids(sql, parameters):
        return sorted(row[0] for row in db.execute(sql, parameters))

    mismatches = []
    for where in ["s in (?, ?)", "s collate nocase in (?, ?)", "s collate rtrim in (?, ?)", "part in (?, ?)"]:
        for values in [("a\x00b", "zz"), ("a\x00b", "a"), ("A\x00B  ", "a"), ("x" * 4000, "a\x00b"), (1, "x" * 4000), (2.0, "3")]:
            want = rowids(f"select id from plain where {where}", values)
            got = rowids(f"select rowid from v where a match '[0]' and k = 10 and {where}", values)
            if got != want:
                mismatches.append((where, values, got, want))
    assert mismatches == []
    assert rowids("select rowid from v where a match '[0]' and k = 10 and s in (?, ?)", ["a\x00b", "a"]) == [1, 2]
