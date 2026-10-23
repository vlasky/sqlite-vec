# `sqlite-vec` Architecture

Internal documentation for how `sqlite-vec` works under-the-hood. Not meant for
users of the `sqlite-vec` project, consult
[the official `sqlite-vec` documentation](https://alexgarcia.xyz/sqlite-vec) for
how-to-guides. Rather, this is for people interested in how `sqlite-vec` works
and some guidelines to any future contributors.

Very much a WIP.

## `vec0`

### Shadow Tables

#### `xyz_chunks`

- `chunk_id INTEGER`
- `size INTEGER`
- `validity BLOB`
- `rowids BLOB`

#### `xyz_rowids`

- `rowid INTEGER`
- `id`
- `chunk_id INTEGER`
- `chunk_offset INTEGER`

#### `xyz_vector_chunksNN`

- `rowid INTEGER`
- `vector BLOB`

#### `xyz_auxiliary`

- `rowid INTEGER`
- `valueNN [type]`

#### `xyz_metadatachunksNN`

- `rowid INTEGER`
- `data BLOB`

#### `xyz_metadatatextNN`

- `rowid INTEGER`
- `data TEXT`

#### Identifying shadow tables

The supported way to tell which tables belong to a `vec0` table is by name. A
`vec0` table `xyz` owns these tables and no others (`NN` is two digits):

- `xyz_info`, `xyz_chunks`, `xyz_rowids`: always
- `xyz_vector_chunksNN`: one per vector column
- `xyz_auxiliary`: only if there are auxiliary columns
- `xyz_metadatachunksNN`: one per metadata column
- `xyz_metadatatextNN`: one per text metadata column

This query lists them for every `vec0` table in a database. It reads only
`sqlite_master`, so it works on every SQLite version and on a connection that
has not loaded `sqlite-vec`:

```sql
select v.name as vec0_table, s.name as backing_table
from sqlite_master as v
join sqlite_master as s
  on s.type = 'table'
 and substr(s.name, 1, length(v.name) + 1) = v.name || '_'
 and (substr(s.name, length(v.name) + 2) in ('rowids', 'chunks', 'info', 'auxiliary')
   or substr(s.name, length(v.name) + 2) glob 'vector_chunks[0-9][0-9]'
   or substr(s.name, length(v.name) + 2) glob 'metadatachunks[0-9][0-9]'
   or substr(s.name, length(v.name) + 2) glob 'metadatatext[0-9][0-9]')
where v.type = 'table' and v.rootpage = 0
  and v.sql like 'create virtual table%using vec0%'
order by 1, 2;
```

`type = 'shadow'` in `PRAGMA table_list` is best-effort and should not be
relied on:

- A connection that has not loaded `sqlite-vec` reports every backing table as
  `table`.
- Up to SQLite 3.53, so does a connection that parsed the schema before loading
  the extension.
- Before SQLite 3.37 there is no `PRAGMA table_list` and no prefix marking (see
  below), so the vector chunk tables are never shadow tables.
- SQLite finds the virtual table that owns a newly created or newly parsed
  table by splitting its name at the **last** underscore
  ([documented](https://www.sqlite.org/vtab.html#the_xshadowname_method)). For
  `xyz_vector_chunks00` it looks for a virtual table called `xyz_vector`, so
  `xShadowName` is never asked about it on that path.
- `xShadowName` does report `vector_chunksNN`, and SQLite also marks shadow
  tables by name prefix when it parses the virtual table's own schema entry.
  That only sees tables parsed earlier, which in practice means after a
  `VACUUM` (it rewrites `sqlite_master` with virtual tables last). A `vec0`
  table created after that `VACUUM` is not covered until the next one.
- SQLite 3.54 additionally marks by prefix after every `xConnect`. There the
  vector chunk tables become `shadow` once the `vec0` table has been used in
  the connection, except in the connection that created it. `PRAGMA
  table_list` connects every virtual table first, so it always reports them as
  `shadow`, but under `SQLITE_DBCONFIG_DEFENSIVE` a direct write to a chunk
  table is still accepted until the `vec0` table is first touched. This prefix
  matching is not part of the documented contract.

Rules that follow from this:

- A new backing table that has no upstream counterpart should use a suffix
  without underscores (`metadatachunksNN`, not `metadata_chunksNN`), so that it
  follows the documented rule. A table ported from upstream keeps upstream's
  name, to stay file-compatible, and is added to `vec0ShadowName`.
- `xyz_vector_chunksNN` is not renamed, because that would make databases
  unreadable by upstream `sqlite-vec` and by earlier releases of this fork.
- Do not rename a backing table from inside `xConnect`. With a minimal module
  under AddressSanitizer on SQLite 3.45.3, an `ALTER TABLE ... RENAME` issued
  there was a heap-use-after-free in the statement that triggered the connect.

### idxStr

The `vec0` idxStr is a string composed of single "header" character and 0 or
more "blocks" of 4 characters each.

The "header" charcter denotes the type of query plan, as determined by the
`enum vec0_query_plan` values. The current possible values are:

| Name                       | Value | Description                                                            |
| -------------------------- | ----- | ---------------------------------------------------------------------- |
| `VEC0_QUERY_PLAN_FULLSCAN` | `'1'` | Perform a full-scan on all rows                                        |
| `VEC0_QUERY_PLAN_POINT`    | `'2'` | Perform a single-lookup point query for the provided rowid             |
| `VEC0_QUERY_PLAN_KNN`      | `'3'` | Perform a KNN-style query on the provided query vector and parameters. |

Each 4-character "block" is associated with a corresponding value in `argv[]`.
For example, the 1st block at byte offset `1-4` (inclusive) is the 1st block and
is associated with `argv[1]`. The 2nd block at byte offset `5-8` (inclusive) is
associated with `argv[2]` and so on. Each block describes what kind of value or
filter the given `argv[i]` value is.

#### `VEC0_IDXSTR_KIND_KNN_MATCH` (`'{'`)

`argv[i]` is the query vector of the KNN query.

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_KNN_K` (`'}'`)

`argv[i]` is the limit/k value of the KNN query.

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_KNN_ROWID_IN` (`'['`)

`argv[i]` is the optional `rowid in (...)` value, and must be handled with
[`sqlite3_vtab_in_first()` / `sqlite3_vtab_in_next()`](https://www.sqlite.org/c3ref/vtab_in_first.html).

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_KNN_PARTITON_CONSTRAINT` (`']'`)

`argv[i]` is a "constraint" on a specific partition key.

The second character of the block denotes which partition key to filter on,
using `A` to denote the first partition key column, `B` for the second, etc. It
is encoded with `'A' + partition_idx` and can be decoded with `c - 'A'`.

The third character of the block denotes which operator is used in the
constraint. It will be one of the values of `enum vec0_partition_operator`, as
only a subset of operations are supported on partition keys.

The fourth character of the block is a `_` filler.

#### `VEC0_IDXSTR_KIND_POINT_ID` (`'!'`)

`argv[i]` is the value of the rowid or id to match against for the point query.

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_METADATA_CONSTRAINT` (`'&'`)

`argv[i]` is the value of the `WHERE` constraint for a metdata column in a KNN
query.

The second character of the block denotes which metadata column the constraint
belongs to, using `A` to denote the first metadata column column, `B` for the
second, etc. It is encoded with `'A' + metadata_idx` and can be decoded with
`c - 'A'`.

The third character of the block is the constraint operator. It will be one of
`enum vec0_metadata_operator`, as only a subset of operators are supported on
metadata column KNN filters.

The fourth character of the block is the collation the constraint compares text
under, one of `enum vec0_collation`: `_` for BINARY, `n` for NOCASE and `r` for
RTRIM. Constraints on non-text columns always carry `_`.

Each claimed constraint keeps exactly the rows SQLite would keep, so vec0 sets
`omit` and SQLite may skip checking it again. A few constraints cannot be
checked exactly before the k nearest rows are chosen: `!=` and `IS NOT` under a
collation other than BINARY (SQLite hands those operators to a virtual table
without their left operand, so the collation is unknown), and `LIKE` and `GLOB`,
which vec0 matches with `sqlite3_strlike()` and `sqlite3_strglob()` before the
k are chosen and SQLite's own `like()` and `glob()` decide afterwards, so
`PRAGMA case_sensitive_like` is honoured. For those vec0 keeps a superset of
the rows, leaves `omit` unset, and SQLite re-checks each of the k nearest rows
afterwards. Such a query returns the nearest rows that satisfy the constraint,
but possibly fewer than k of them; a larger k recovers the rest. Two cases are
not recovered by a larger k: an application's replacement `like()` or `glob()`
that accepts rows the built-in matching rejects, since those rows are never
candidates, and `x IN (SELECT ... COLLATE y)`, which SQLite compares under the
subquery's collation while `sqlite3_vtab_collation()` reports the left
operand's, so vec0 compares under the left operand's and drops rows SQLite
would keep. Name the collation on the left operand instead. vec0 implements
NOCASE and RTRIM itself, so an application that replaces either built-in
collation is not honoured. A constraint's value takes the metadata column's
affinity, as R-Tree's do; SQLite instead applies numeric affinity when a text
column is compared with an integer or real column of another table, so a join
condition such as `v.t = nums.n` can keep a row (`'05'` against 5) that vec0
drops, as it did before this change.

#### `VEC0_IDXSTR_KIND_KNN_DISTANCE_CONSTRAINT` (`'*'`)

`argv[i]` is a constraint on the `distance` column in a KNN query.

This enables filtering KNN results by distance thresholds, useful for:
- Cursor-based pagination: `WHERE embedding MATCH ? AND k = 10 AND distance > 0.21`
- Range queries: `WHERE embedding MATCH ? AND k = 100 AND distance BETWEEN 0.5 AND 1.0`

The second character of the block denotes the constraint operator. It will be one of
the values of `enum vec0_distance_constraint_operator`:

| Operator | Value | Description              | SQL Example          |
| -------- | ----- | ------------------------ | -------------------- |
| `GT`     | `'a'` | Greater than             | `distance > 0.5`     |
| `GE`     | `'b'` | Greater than or equal to | `distance >= 0.5`    |
| `LT`     | `'c'` | Less than                | `distance < 1.0`     |
| `LE`     | `'d'` | Less than or equal to    | `distance <= 1.0`    |

The third and fourth characters of the block are `_` fillers.

**Note on precision:** A row's f32 distance is widened to double and compared with
the double SQLite received for the threshold, so a threshold a hair above or
below a row's distance keeps or drops the row exactly as SQLite's own check
would.

**Note on pagination:** When multiple vectors have identical distances, pagination using
`distance > X` may skip some results. For stable pagination, combine distance with rowid:
`WHERE (distance > 0.5) OR (distance = 0.5 AND rowid > 123)`
