import sqlite3

import pytest

# Element-type spellings that vec0 must accept in a vector column definition.
# `float32` is undocumented but has always been accepted (it prefix-matched
# "float"), so it stays supported to avoid a silent regression.
VALID_TYPE_DEFS = [
    "float[2]",
    "f32[2]",
    "float32[2]",
    "int8[2]",
    "i8[2]",
    "bit[8]",
]

# Malformed type names that merely share a prefix with a valid element type.
# vec0 used a prefix-only strnicmp match and silently coerced these to the
# prefix's type (e.g. `float16` -> float32, `bitcoin` -> bit). That hides typos
# and would silently shadow real future types like float16/bfloat16, so the
# parser must reject any identifier that is not an exact element-type spelling.
INVALID_TYPE_DEFS = [
    "floaty[2]",
    "floating[2]",
    "float16[2]",
    "f32x[2]",
    "int8_t[2]",
    "int8garbage[2]",
    "i8x[2]",
    "bitcoin[2]",
    "bits[2]",
    "bfloat16[2]",
    # names the metadata parser would accept: with the brackets they are
    # vector definitions with an unknown type, and must not become a
    # metadata column (a table reopened that way would read the wrong
    # shadow tables)
    "float64[2]",
    "double[2]",
    "f64[2]",
    "int64[2]",
    "int[2]",
    "integer[2]",
    "text[2]",
    "boolean[2]",
]


@pytest.mark.parametrize("type_def", VALID_TYPE_DEFS)
def test_valid_vector_column_types_accepted(db, type_def):
    db.execute(f"create virtual table t using vec0(a {type_def})")


@pytest.mark.parametrize("type_def", INVALID_TYPE_DEFS)
def test_malformed_vector_column_types_rejected(db, type_def):
    with pytest.raises(sqlite3.OperationalError, match="could not parse vector column"):
        db.execute(f"create virtual table t using vec0(a {type_def})")
    # also when another, valid vector column follows
    with pytest.raises(sqlite3.OperationalError, match="could not parse vector column"):
        db.execute(f"create virtual table t using vec0(a {type_def}, b float[2])")
