import sqlite3
import struct


def _f32(values):
    return struct.pack("%sf" % len(values), *values)


def _int8(values):
    return struct.pack("%sb" % len(values), *values)


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


def test_delete_zeroes_rowid_blob(db):
    db.execute("create virtual table v using vec0(emb float[4], chunk_size=8)")

    for i in range(1, 4):
        db.execute(
            "insert into v(rowid, emb) values (?, ?)",
            [i, _f32([float(i)] * 4)],
        )

    db.execute("delete from v where rowid = 2")

    blob = db.execute("select rowids from v_chunks where rowid = 1").fetchone()[0]
    rowids = struct.unpack("<8q", blob)
    assert rowids[0] == 1  # slot 0 intact
    assert rowids[1] == 0  # slot 1 zeroed (was rowid 2)
    assert rowids[2] == 3  # slot 2 intact


def test_delete_zeroes_vector_blob(db):
    db.execute("create virtual table v using vec0(emb float[4], chunk_size=8)")

    db.execute(
        "insert into v(rowid, emb) values (1, ?)", [_f32([1.0, 2.0, 3.0, 4.0])]
    )
    db.execute(
        "insert into v(rowid, emb) values (2, ?)", [_f32([5.0, 6.0, 7.0, 8.0])]
    )

    db.execute("delete from v where rowid = 1")

    blob = db.execute(
        "select vectors from v_vector_chunks00 where rowid = 1"
    ).fetchone()[0]
    # First slot (4 floats = 16 bytes) should be zeroed
    first_slot = struct.unpack("<4f", blob[:16])
    assert first_slot == (0.0, 0.0, 0.0, 0.0)
    # Second slot should be unchanged
    second_slot = struct.unpack("<4f", blob[16:32])
    assert second_slot == (5.0, 6.0, 7.0, 8.0)


def test_delete_all_rows_deletes_chunk(db):
    db.execute("create virtual table v using vec0(emb float[4], chunk_size=8)")

    for i in range(1, 9):
        db.execute(
            "insert into v(rowid, emb) values (?, ?)",
            [i, _f32([float(i)] * 4)],
        )

    for i in range(1, 9):
        db.execute("delete from v where rowid = ?", [i])

    assert db.execute("select count(*) from v_chunks").fetchone()[0] == 0
    assert db.execute("select count(*) from v_vector_chunks00").fetchone()[0] == 0

    # Inserting after full deletion still works
    db.execute(
        "insert into v(rowid, emb) values (100, ?)", [_f32([9.0, 9.0, 9.0, 9.0])]
    )
    row = db.execute("select emb from v where rowid = 100").fetchone()
    assert row[0] == _f32([9.0, 9.0, 9.0, 9.0])


def test_delete_chunk_multiple_chunks(db):
    db.execute("create virtual table v using vec0(emb float[4], chunk_size=8)")

    for i in range(1, 17):
        db.execute(
            "insert into v(rowid, emb) values (?, ?)",
            [i, _f32([float(i)] * 4)],
        )

    # Delete all rows from the first chunk (rows 1-8)
    for i in range(1, 9):
        db.execute("delete from v where rowid = ?", [i])

    # Only 1 chunk should remain
    assert db.execute("select count(*) from v_chunks").fetchone()[0] == 1

    # Rows 9-16 still queryable
    for i in range(9, 17):
        row = db.execute("select emb from v where rowid = ?", [i]).fetchone()
        assert row[0] == _f32([float(i)] * 4)


def test_delete_with_metadata_columns(db):
    db.execute(
        "create virtual table v using vec0("
        "emb float[4], "
        "m_bool boolean, "
        "m_int integer, "
        "m_float float, "
        "m_text text, "
        "chunk_size=8"
        ")"
    )

    for i in range(1, 9):
        db.execute(
            "insert into v(rowid, emb, m_bool, m_int, m_float, m_text) "
            "values (?, ?, ?, ?, ?, ?)",
            [i, _f32([float(i)] * 4), i % 2 == 0, i * 10, float(i) / 2.0, f"text_{i}"],
        )

    for i in range(1, 9):
        db.execute("delete from v where rowid = ?", [i])

    assert db.execute("select count(*) from v_chunks").fetchone()[0] == 0
    assert db.execute("select count(*) from v_vector_chunks00").fetchone()[0] == 0
    assert db.execute("select count(*) from v_metadatachunks00").fetchone()[0] == 0
    assert db.execute("select count(*) from v_metadatachunks01").fetchone()[0] == 0
    assert db.execute("select count(*) from v_metadatachunks02").fetchone()[0] == 0
    assert db.execute("select count(*) from v_metadatachunks03").fetchone()[0] == 0


def test_delete_with_auxiliary_columns(db):
    db.execute(
        "create virtual table v using vec0("
        "emb float[4], "
        "+aux_text text, "
        "chunk_size=8"
        ")"
    )

    for i in range(1, 9):
        db.execute(
            "insert into v(rowid, emb, aux_text) values (?, ?, ?)",
            [i, _f32([float(i)] * 4), f"aux_{i}"],
        )

    for i in range(1, 9):
        db.execute("delete from v where rowid = ?", [i])

    assert db.execute("select count(*) from v_chunks").fetchone()[0] == 0
    assert db.execute("select count(*) from v_auxiliary").fetchone()[0] == 0


def test_delete_with_text_primary_key(db):
    db.execute(
        "create virtual table v using vec0("
        "id text primary key, emb float[4], chunk_size=8"
        ")"
    )

    db.execute(
        "insert into v(id, emb) values ('a', ?)", [_f32([1.0, 2.0, 3.0, 4.0])]
    )
    db.execute(
        "insert into v(id, emb) values ('b', ?)", [_f32([5.0, 6.0, 7.0, 8.0])]
    )

    db.execute("delete from v where id = 'a'")

    # Vector blob slot 0 should be zeroed
    blob = db.execute(
        "select vectors from v_vector_chunks00 where rowid = 1"
    ).fetchone()[0]
    first_slot = struct.unpack("<4f", blob[:16])
    assert first_slot == (0.0, 0.0, 0.0, 0.0)

    # Remaining row still queryable
    row = db.execute("select emb from v where id = 'b'").fetchone()
    assert row[0] == _f32([5.0, 6.0, 7.0, 8.0])


def test_delete_with_partition_keys(db):
    db.execute(
        "create virtual table v using vec0("
        "part text partition key, emb float[4], chunk_size=8"
        ")"
    )

    for i in range(1, 9):
        db.execute(
            "insert into v(rowid, part, emb) values (?, 'A', ?)",
            [i, _f32([float(i)] * 4)],
        )
    for i in range(9, 17):
        db.execute(
            "insert into v(rowid, part, emb) values (?, 'B', ?)",
            [i, _f32([float(i)] * 4)],
        )

    # Delete all from partition A
    for i in range(1, 9):
        db.execute("delete from v where rowid = ?", [i])

    # 1 chunk should remain (partition B's)
    assert db.execute("select count(*) from v_chunks").fetchone()[0] == 1

    # Partition B rows intact
    for i in range(9, 17):
        row = db.execute("select emb from v where rowid = ?", [i]).fetchone()
        assert row[0] == _f32([float(i)] * 4)

    # Re-insert into partition A works
    db.execute(
        "insert into v(rowid, part, emb) values (100, 'A', ?)",
        [_f32([99.0, 99.0, 99.0, 99.0])],
    )
    row = db.execute("select emb from v where rowid = 100").fetchone()
    assert row[0] == _f32([99.0, 99.0, 99.0, 99.0])


def test_delete_int8_vectors(db):
    db.execute("create virtual table v using vec0(emb int8[4], chunk_size=8)")

    db.execute(
        "insert into v(rowid, emb) values (1, vec_int8(?))",
        [_int8([1, 2, 3, 4])],
    )
    db.execute(
        "insert into v(rowid, emb) values (2, vec_int8(?))",
        [_int8([5, 6, 7, 8])],
    )

    db.execute("delete from v where rowid = 1")

    blob = db.execute(
        "select vectors from v_vector_chunks00 where rowid = 1"
    ).fetchone()[0]
    # int8[4] = 4 bytes per slot
    first_slot = struct.unpack("<4b", blob[:4])
    assert first_slot == (0, 0, 0, 0)
    second_slot = struct.unpack("<4b", blob[4:8])
    assert second_slot == (5, 6, 7, 8)


def test_delete_bit_vectors(db):
    db.execute("create virtual table v using vec0(emb bit[8], chunk_size=8)")

    db.execute(
        "insert into v(rowid, emb) values (1, vec_bit(?))",
        [bytes([0xFF])],
    )
    db.execute(
        "insert into v(rowid, emb) values (2, vec_bit(?))",
        [bytes([0xAA])],
    )

    db.execute("delete from v where rowid = 1")

    blob = db.execute(
        "select vectors from v_vector_chunks00 where rowid = 1"
    ).fetchone()[0]
    # bit[8] = 1 byte per slot
    assert blob[0:1] == bytes([0x00])
    assert blob[1:2] == bytes([0xAA])


def _file_db(tmp_path):
    """Open a file-backed DB (required for page_count to shrink after VACUUM)."""
    db = sqlite3.connect(str(tmp_path / "test.db"))
    db.row_factory = sqlite3.Row
    db.enable_load_extension(True)
    db.load_extension("dist/vec0")
    db.enable_load_extension(False)
    return db


def test_delete_chunk_shrinks_pages(tmp_path):
    """Use large vectors (float[256]) so each chunk blob spans multiple pages,
    making the page_count difference measurable after VACUUM."""
    dims = 256
    db = _file_db(tmp_path)
    db.execute(f"create virtual table v using vec0(emb float[{dims}], chunk_size=8)")

    for i in range(1, 25):  # 3 full chunks of 8
        db.execute(
            "insert into v(rowid, emb) values (?, ?)",
            [i, _f32([float(i)] * dims)],
        )
    db.commit()
    pages_before = db.execute("pragma page_count").fetchone()[0]

    # Delete all rows
    for i in range(1, 25):
        db.execute("delete from v where rowid = ?", [i])
    db.commit()

    assert db.execute("select count(*) from v_chunks").fetchone()[0] == 0

    db.execute("vacuum")
    pages_after = db.execute("pragma page_count").fetchone()[0]
    assert pages_after < pages_before, (
        f"page_count should shrink after deleting all chunks and vacuum: "
        f"{pages_before} -> {pages_after}"
    )
    db.close()


def test_delete_one_chunk_of_two_shrinks_pages(tmp_path):
    """Use large vectors (float[256]) so each chunk blob spans multiple pages,
    making the page_count difference measurable after VACUUM."""
    dims = 256
    db = _file_db(tmp_path)
    db.execute(f"create virtual table v using vec0(emb float[{dims}], chunk_size=8)")

    for i in range(1, 17):  # 2 full chunks of 8
        db.execute(
            "insert into v(rowid, emb) values (?, ?)",
            [i, _f32([float(i)] * dims)],
        )
    db.commit()
    pages_before = db.execute("pragma page_count").fetchone()[0]

    # Delete all rows from the first chunk (rows 1-8)
    for i in range(1, 9):
        db.execute("delete from v where rowid = ?", [i])
    db.commit()

    assert db.execute("select count(*) from v_chunks").fetchone()[0] == 1

    db.execute("vacuum")
    pages_after = db.execute("pragma page_count").fetchone()[0]
    assert pages_after < pages_before, (
        f"page_count should shrink after deleting one of two chunks and vacuum: "
        f"{pages_before} -> {pages_after}"
    )
    db.close()
