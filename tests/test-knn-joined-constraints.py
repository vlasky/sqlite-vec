import sqlite3

import pytest

# Six points on a line, the first three tagged 1 and in partition 1, the rest
# tagged 2 and in partition 2, so the k = 2 nearest the origin are rowids 1 and
# 2 overall, 4 and 5 among tag 2, and 1 and 6 with mmr_lambda = 0.3.


@pytest.fixture()
def fill(db):
    db.execute(
        "create virtual table v using vec0("
        "part integer partition key, embedding float[2] distance_metric=l2, tag integer)"
    )
    db.executemany(
        "insert into v(rowid, part, embedding, tag) values (?, ?, ?, ?)",
        [[i, 1 if i <= 3 else 2, f"[{i},0]", 1 if i <= 3 else 2] for i in range(1, 7)],
    )
    db.execute("create table w(q text, n integer, lambda real)")
    db.execute("insert into w values ('[0,0]', 2, 0.3)")
    db.execute(
        "create table categories(id integer primary key, q text, n integer, lambda real)"
    )
    db.execute(
        "insert into categories values (1, '[0,0]', 2, 1.0), (2, '[0,0]', 2, 1.0)"
    )
    return db


def rowids(db, sql):
    return [row[0] for row in db.execute(sql)]


@pytest.mark.parametrize("tables", ["w, v", "v, w"])
def test_the_query_vector_can_come_from_another_table(fill, tables):
    knn = f"select v.rowid from {tables} where v.embedding match w.q and v.k = 2"
    assert rowids(fill, knn) == [1, 2]


@pytest.mark.parametrize("tables", ["w, v", "v, w"])
def test_k_can_come_from_another_table(fill, tables):
    knn = f"select v.rowid from {tables} where v.embedding match '[0,0]' and v.k = w.n"
    assert rowids(fill, knn) == [1, 2]


@pytest.mark.parametrize("tables", ["w, v", "v, w"])
def test_mmr_lambda_can_come_from_another_table(fill, tables):
    knn = (
        f"select v.rowid from {tables} where v.embedding match '[0,0]' and v.k = 2 "
        "and v.mmr_lambda = w.lambda"
    )
    assert rowids(fill, knn) == [1, 6]


# A table that supplies the query vector, k or mmr_lambda is read before v, so
# vec0 runs one KNN per row of it, and a filter whose value comes from that
# table applies before the k: the 2 nearest in each category.
@pytest.mark.parametrize(
    "arguments",
    [
        "v.embedding match c.q and v.k = 2",
        "v.embedding match '[0,0]' and v.k = c.n",
        "v.embedding match '[0,0]' and v.k = 2 and v.mmr_lambda = c.lambda",
    ],
)
@pytest.mark.parametrize("column", ["tag", "part"])
def test_a_table_that_supplies_an_argument_filters_before_the_k(
    fill, column, arguments
):
    knn = (
        f"select c.id, v.rowid from v join categories c on c.id = v.{column} "
        f"where {arguments}"
    )
    assert [tuple(row) for row in fill.execute(knn)] == [(1, 1), (1, 2), (2, 4), (2, 5)]


# A filter whose value comes from a table that supplies no KNN argument runs on
# the k rows the KNN returns, in either FROM order, so a lookup join returns k
# rows. Running one KNN per categories row instead would return k rows per
# category; ARCHITECTURE.md's idxStr section says why vec0 leaves the filter to
# the plan.
@pytest.mark.parametrize(
    "tables",
    [
        "v join categories c on c.id = v.{column}",
        "categories c join v on c.id = v.{column}",
    ],
)
@pytest.mark.parametrize("column", ["tag", "part"])
def test_a_lookup_join_on_a_filter_column_returns_k_rows(fill, column, tables):
    knn = (
        f"select c.id, v.rowid from {tables.format(column=column)} "
        "where v.embedding match '[0,0]' and v.k = 2"
    )
    assert [tuple(row) for row in fill.execute(knn)] == [(1, 1), (1, 2)]


# A usable constraint on the same column supplies the argument, so the plan
# that leaves `v.k = w.n` unusable is kept, as on main, where SQLite codes the
# leftover term as `2 = w.n`.
@pytest.mark.parametrize("tables", ["w, v", "v, w"])
def test_a_duplicate_k_is_supplied_by_the_usable_one(fill, tables):
    knn = (
        f"select v.rowid from {tables} where v.embedding match '[0,0]' "
        "and v.k = 2 and v.k = w.n"
    )
    assert rowids(fill, knn) == [1, 2]


# Each row of a table that supplies the arguments runs its own KNN with its own
# k, including k = 0.
def test_successive_outer_rows_supply_their_own_arguments(fill):
    fill.execute("create table requests(id integer primary key, q text, n integer)")
    fill.execute(
        "insert into requests values (1, '[0,0]', 1), (2, '[7,0]', 0), (3, '[7,0]', 3)"
    )
    knn = (
        "select r.id, v.rowid from requests r, v "
        "where v.embedding match r.q and v.k = r.n"
    )
    assert [tuple(row) for row in fill.execute(knn)] == [(1, 1), (3, 6), (3, 5), (3, 4)]


# A scalar `rowid = ?` serves the point plan only; beside a MATCH it is applied
# to the k rows the KNN returns, so a request for a row outside the k nearest
# finds nothing. `rowid in (...)` is the filter that applies before the k.
def test_a_scalar_rowid_equality_applies_after_the_k(fill):
    fill.execute("create table requests(id integer primary key, q text)")
    fill.execute("insert into requests values (1, '[0,0]'), (6, '[0,0]')")
    knn = (
        "select r.id, v.rowid from requests r, v "
        "where v.embedding match r.q and v.k = 2 and v.rowid = r.id"
    )
    assert [tuple(row) for row in fill.execute(knn)] == [(1, 1)]
    knn = (
        "select r.id, v.rowid from requests r, v "
        "where v.embedding match r.q and v.k = 2 and v.rowid in (r.id)"
    )
    assert [tuple(row) for row in fill.execute(knn)] == [(1, 1), (6, 6)]


# When the table that supplies an argument itself reads v, every plan leaves an
# argument unusable, and the query has no plan.
@pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 26, 0),
    reason="xBestIndex may return SQLITE_CONSTRAINT from SQLite 3.26.0",
)
def test_a_cycle_has_no_plan(fill):
    knn = (
        "select v.rowid from v, json_each('[' || v.tag || ']') j "
        "where v.embedding match '[' || j.value || ',0]' and v.k = 2"
    )
    with pytest.raises(sqlite3.OperationalError, match="no query solution"):
        fill.execute(knn).fetchall()
