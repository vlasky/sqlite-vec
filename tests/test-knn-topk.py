import random
import struct

import numpy as np


def _f32(values):
    return struct.pack(f"{len(values)}f", *values)


def test_knn_returns_the_k_nearest_in_order(db):
    # Distinct distances, so the order is fully determined; k below, at and
    # above the chunk size, with and without a filter that thins the chunks.
    rng = random.Random(5)
    db.execute(
        "create virtual table v using vec0(e float[3], g integer, chunk_size=16)"
    )
    rows = {}
    for i in range(1, 201):
        e = [rng.uniform(-1, 1) for _ in range(3)]
        rows[i] = (e, i % 3)
        db.execute("insert into v(rowid, e, g) values (?, ?, ?)", [i, _f32(e), i % 3])
    for _ in range(10):
        q = [rng.uniform(-1, 1) for _ in range(3)]
        for k in (1, 2, 7, 16, 17, 64, 200, 300):
            for g in (None, 1):
                kept = [i for i, (_, gi) in rows.items() if g is None or gi != g]
                got = [
                    r[0]
                    for r in db.execute(
                        "select rowid from v where e match ? and k = ?"
                        + ("" if g is None else " and g != ?"),
                        [_f32(q), k] + ([] if g is None else [g]),
                    )
                ]
                expected = sorted(
                    kept,
                    key=lambda i: db.execute(
                        "select vec_distance_l2(?, ?)", [_f32(q), _f32(rows[i][0])]
                    ).fetchone()[0],
                )[:k]
                assert got == expected


def test_knn_ties_keep_their_order(db):
    # Equal distances come back chunk by chunk, each chunk's rows from its last
    # slot to its first, whether or not k cuts the ties short.
    db.execute("create virtual table v using vec0(e float[2], chunk_size=8)")
    for i in range(1, 21):
        db.execute("insert into v(rowid, e) values (?, ?)", [i, _f32([1, 1])])
    q = _f32([1, 1])

    def knn(k):
        return [
            r[0]
            for r in db.execute("select rowid from v where e match ? and k = ?", [q, k])
        ]

    chunks = [range(8, 0, -1), range(16, 8, -1), range(20, 16, -1)]
    assert knn(20) == [rowid for chunk in chunks for rowid in chunk]
    assert knn(5) == [8, 7, 6, 5, 4]


def test_knn_ranks_a_nan_distance_last(db):
    # vec0 refuses NaN elements, but a static blob reads its vectors from the
    # application's memory as they are, so a distance to one can be NaN.
    db.enable_load_extension(True)
    db.load_extension("dist/vec0", entrypoint="sqlite3_vec_static_blobs_init")
    vectors = np.array([[np.nan, 0], [1, 0], [2, 0], [3, 0]], dtype=np.float32)
    db.execute(
        "insert into temp.vec_static_blobs(name, data)"
        " select 'b', vec_static_blob_from_raw(?, '<f4', 2, 4)",
        [vectors.__array_interface__["data"][0]],
    )
    db.execute("create virtual table b using vec_static_blob_entries(b)")
    rows = db.execute(
        "select rowid from b where vector match ? and k = 4 order by distance",
        [_f32([0, 0])],
    )
    assert [r[0] for r in rows] == [1, 2, 3, 0]


def test_knn_ranks_a_stored_nan_distance_last_across_chunks(db):
    # vec0 has rejected NaN elements since v0.2.6-alpha, but a table written by
    # an earlier release can still hold one. Patching a NaN into the stored
    # chunk stands in for such a table.
    db.execute("create virtual table v using vec0(e float[1], chunk_size=8)")
    for i in range(1, 9):
        db.execute("insert into v(rowid, e) values (?, ?)", [i, _f32([10 + i])])
    for i in range(9, 17):
        db.execute("insert into v(rowid, e) values (?, ?)", [i, _f32([1])])
    chunk_id, offset = db.execute(
        "select chunk_id, chunk_offset from v_rowids where rowid = 16"
    ).fetchone()
    vectors = bytearray(
        db.execute(
            "select vectors from v_vector_chunks00 where rowid = ?", [chunk_id]
        ).fetchone()[0]
    )
    vectors[offset * 4 : offset * 4 + 4] = _f32([float("nan")])
    db.execute(
        "update v_vector_chunks00 set vectors = ? where rowid = ?",
        [bytes(vectors), chunk_id],
    )

    def knn(k):
        return [
            r[0]
            for r in db.execute(
                "select rowid from v where e match ? and k = ?", [_f32([0]), k]
            )
        ]

    # The NaN, in the second chunk, ranks after the first chunk's rows too.
    assert knn(16) == [15, 14, 13, 12, 11, 10, 9, 1, 2, 3, 4, 5, 6, 7, 8, 16]
    assert knn(9) == [15, 14, 13, 12, 11, 10, 9, 1, 2]
