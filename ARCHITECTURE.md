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

A KNN plan needs its arguments: the MATCH on a vector column, `k`, and the
hidden parameter columns declared after `k` (`mmr_lambda` among them). When one
of them reads another table of the query, SQLite also weighs plans that scan
`vec0` before that table, in which the argument is unusable. `xBestIndex`
returns `SQLITE_CONSTRAINT` for such a plan (`vec0_constraint_is_knn_argument`),
so the planner takes one that gives `vec0` every argument, unless a usable
constraint supplies the same argument, as `k = 2` does beside `k = w.n`
(`vec0_knn_argument_is_supplied`). SQLite accepts `SQLITE_CONSTRAINT` from
`xBestIndex` from 3.26.0 on, so on an older library every plan is kept, as
before. A query in which the table that supplies an argument itself reads `vec0`
(a cycle, such as `v.k = j.value` with `j` a `json_each` over a column of `v`)
has no plan at all and fails with "no query solution".

Filters on rowid `IN (...)`, partition key, metadata and distance columns are
left to the plan. A filter whose value comes from another table is unusable in a
plan that scans `vec0` first, and SQLite can take such a plan in either FROM
order, applying the filter to the k rows `vec0` returns. That keeps a lookup
join at k rows, and `vec0` cannot tell a lookup join from a filter join: in

```sql
select v.rowid, c.name from v join categories c on c.id = v.category
where v.embedding match ? and k = 10
```

refusing the plan without `v.category = c.id` would run one KNN per
`categories` row and return 10 rows per category. A query that reads the other
table first, because that table supplies a KNN argument, a `CROSS JOIN` names it
first, or `vec0` is on the right of a `LEFT JOIN` with the filter in `ON`, has
the filter usable in every plan, so `vec0` runs once per row of that table and
applies the filter before the k. So does a correlated subquery, whose outer
columns are constants to `vec0`.

Which plan a lookup join gets is the planner's choice, made from costs and
statistics, not a guarantee: after `ANALYZE`, a small `categories` table can
become the outer loop of the query above, so that `vec0` runs once per category
and the join returns 10 rows per category. A query that needs a global k should
run the KNN in a subquery or CTE and join its result.

A scalar `rowid = ?` beside a MATCH is not one of the filters above: only
`rowid IN (...)` is pushed into candidate selection, and `rowid = ?` serves the
point plan alone, so with a MATCH and `k` the k nearest rows are selected first
and SQLite then keeps only the one with that rowid, if it is among them.

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

The foruth character of the block is a `_` filler.

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

**Note on precision:** Distance values are cast from f64 to f32 for comparison, which may
result in precision loss for very small distance differences.

**Note on pagination:** When multiple vectors have identical distances, pagination using
`distance > X` may skip some results. For stable pagination, combine distance with rowid:
`WHERE (distance > 0.5) OR (distance = 0.5 AND rowid > 123)`
