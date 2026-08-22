import struct


def _f32(values):
    return struct.pack("%sf" % len(values), *values)


def test_insert_or_replace_integer_pk(db):
    """INSERT OR REPLACE should update vector when rowid already exists."""
    db.execute("create virtual table v using vec0(emb float[4], chunk_size=8)")

    db.execute(
        "insert into v(rowid, emb) values (1, ?)", [_f32([1.0, 2.0, 3.0, 4.0])]
    )
    # Replace with new vector
    db.execute(
        "insert or replace into v(rowid, emb) values (1, ?)",
        [_f32([10.0, 20.0, 30.0, 40.0])],
    )

    # Should still have exactly 1 row
    count = db.execute("select count(*) from v").fetchone()[0]
    assert count == 1

    # Vector should be the replaced value
    row = db.execute("select emb from v where rowid = 1").fetchone()
    assert row[0] == _f32([10.0, 20.0, 30.0, 40.0])


def test_insert_or_replace_new_row(db):
    """INSERT OR REPLACE with a new rowid should just insert normally."""
    db.execute("create virtual table v using vec0(emb float[4], chunk_size=8)")

    db.execute(
        "insert or replace into v(rowid, emb) values (1, ?)",
        [_f32([1.0, 2.0, 3.0, 4.0])],
    )

    count = db.execute("select count(*) from v").fetchone()[0]
    assert count == 1

    row = db.execute("select emb from v where rowid = 1").fetchone()
    assert row[0] == _f32([1.0, 2.0, 3.0, 4.0])


def test_insert_or_replace_text_pk(db):
    """INSERT OR REPLACE should work with text primary keys."""
    db.execute(
        "create virtual table v using vec0("
        "id text primary key, emb float[4], chunk_size=8"
        ")"
    )

    db.execute(
        "insert into v(id, emb) values ('doc_a', ?)",
        [_f32([1.0, 2.0, 3.0, 4.0])],
    )
    db.execute(
        "insert or replace into v(id, emb) values ('doc_a', ?)",
        [_f32([10.0, 20.0, 30.0, 40.0])],
    )

    count = db.execute("select count(*) from v").fetchone()[0]
    assert count == 1

    row = db.execute("select emb from v where id = 'doc_a'").fetchone()
    assert row[0] == _f32([10.0, 20.0, 30.0, 40.0])


def test_insert_or_replace_with_auxiliary(db):
    """INSERT OR REPLACE should also replace auxiliary column values."""
    db.execute(
        "create virtual table v using vec0("
        "emb float[4], +label text, chunk_size=8"
        ")"
    )

    db.execute(
        "insert into v(rowid, emb, label) values (1, ?, 'old')",
        [_f32([1.0, 2.0, 3.0, 4.0])],
    )
    db.execute(
        "insert or replace into v(rowid, emb, label) values (1, ?, 'new')",
        [_f32([10.0, 20.0, 30.0, 40.0])],
    )

    count = db.execute("select count(*) from v").fetchone()[0]
    assert count == 1

    row = db.execute("select emb, label from v where rowid = 1").fetchone()
    assert row[0] == _f32([10.0, 20.0, 30.0, 40.0])
    assert row[1] == "new"


def test_insert_or_replace_with_metadata(db):
    """INSERT OR REPLACE should also replace metadata column values."""
    db.execute(
        "create virtual table v using vec0("
        "emb float[4], tag text, chunk_size=8"
        ")"
    )

    db.execute(
        "insert into v(rowid, emb, tag) values (1, ?, 'old-metadata-value-that-is-long')",
        [_f32([1.0, 2.0, 3.0, 4.0])],
    )
    db.execute(
        "insert or replace into v(rowid, emb, tag) values (1, ?, 'new-metadata-value-that-is-long')",
        [_f32([10.0, 20.0, 30.0, 40.0])],
    )

    count = db.execute("select count(*) from v").fetchone()[0]
    assert count == 1

    row = db.execute("select tag from v where rowid = 1").fetchone()
    assert row[0] == "new-metadata-value-that-is-long"
    assert (
        db.execute(
            "select rowid from v where emb match ? and k = 1 and tag = 'new-metadata-value-that-is-long'",
            [_f32([10.0, 20.0, 30.0, 40.0])],
        ).fetchone()[0]
        == 1
    )


def test_insert_or_replace_knn_uses_new_vector(db):
    """After INSERT OR REPLACE, KNN should find the new vector, not the old one."""
    db.execute("create virtual table v using vec0(emb float[4], chunk_size=8)")

    db.execute(
        "insert into v(rowid, emb) values (1, ?)", [_f32([1.0, 0.0, 0.0, 0.0])]
    )
    db.execute(
        "insert into v(rowid, emb) values (2, ?)", [_f32([0.0, 1.0, 0.0, 0.0])]
    )

    # Replace row 1's vector to be very close to row 2
    db.execute(
        "insert or replace into v(rowid, emb) values (1, ?)",
        [_f32([0.0, 0.9, 0.0, 0.0])],
    )

    # KNN for [0, 1, 0, 0] should return row 2 first (exact), then row 1 (close)
    rows = db.execute(
        "select rowid, distance from v where emb match ? and k = 2",
        [_f32([0.0, 1.0, 0.0, 0.0])],
    ).fetchall()
    assert rows[0][0] == 2
    assert rows[1][0] == 1
    assert rows[1][1] < 0.11  # should be close (L2 distance ≈ 0.1)
