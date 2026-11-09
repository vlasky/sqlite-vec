# Changelog

All notable changes to this community fork will be documented in this file.

## [0.2.9-alpha] - 2026-11-09

Fixes for open upstream bug reports, checked against this fork and found to apply, plus three open upstream PRs ported as they stand.

### Fixed

- **A failed INSERT no longer leaves a ghost row** (upstream [#333](https://github.com/asg017/sqlite-vec/issues/333), ports upstream PR [#360](https://github.com/asg017/sqlite-vec/pull/360) and extends it to auxiliary columns) - metadata and auxiliary column types are checked before anything is written, so a rejected INSERT inside a transaction no longer leaves a searchable row that survives COMMIT; UPDATE likewise checks its new metadata, auxiliary and vector values before it writes anything, so a rejected UPDATE changes nothing
- **`part in (1, 2)` on a partition key returns the k nearest rows overall** (upstream [#142](https://github.com/asg017/sqlite-vec/issues/142)) - the list used to reach xFilter once per value, each returning its own k rows; it is now one membership test on the chunks query, with the column's affinity and collation, on SQLite 3.38 or later. The list's values are converted before they are copied: `sqlite3_value_numeric_type()` on a copy dereferences a NULL connection in SQLite 3.53.0 and 3.53.1 THREADSAFE builds (the ones current Python builds ship; fixed in SQLite 3.54.0)
- **UPDATE on a partition-keyed table works with any WHERE clause** (upstream [#261](https://github.com/asg017/sqlite-vec/issues/261)) - full-scan and KNN plans handed xUpdate the current partition key as a new value, so every UPDATE that was not `WHERE rowid = ?` failed with "UPDATE on partition key columns are not supported yet"; unchanged partition, auxiliary and metadata columns are now reported as unchanged on every plan (vectors keep the existing NULL convention)
- **UPDATE and DELETE driven by a KNN query** - `delete from t where v match ? and k = 1` failed with "expected point query plan in vec0Rowid" on tables without a declared primary key column
- **`UPDATE t SET rowid = 9` is refused** (upstream [#332](https://github.com/asg017/sqlite-vec/issues/332)) - it used to report one changed row and change nothing; moving a row to another rowid is not implemented, and the error now matches the text primary key case
- **L2 distance for very large and very small float32 differences** (upstream [#334](https://github.com/asg017/sqlite-vec/issues/334), [#335](https://github.com/asg017/sqlite-vec/issues/335)) - the float32 sum of squares overflowed to Inf above about 1.8e19 and underflowed to 0 below about 1e-19, in `vec_distance_l2()` and L2 KNN queries; those sums are redone in double, ordinary vectors keep the same fast path and results
- **Raw int8 and bit vectors are accepted by their columns** (upstream [#361](https://github.com/asg017/sqlite-vec/issues/361)) - a BLOB without a vector subtype whose size is exactly the column's is stored as the column's kind of vector, and accepted as a KNN query vector for it, instead of being read as float32 and rejected with a misleading error; this also lets `UPDATE ... FROM` on int8 and bit tables leave the vector alone, since SQLite hands back the stored blob there without the unchanged flag
- **BOOLEAN metadata values are checked in full** - `4294967297` used to pass the 0-or-1 check as 1 after truncation to 32 bits
- **`vec_each()` reads bit vectors least significant bit first** (ports upstream PR [#323](https://github.com/asg017/sqlite-vec/pull/323) by ariannamethod) - matching `vec_to_json()`, `vec_quantize_binary()` and the stored bitmaps; the API reference example is corrected
- **`vec_distance_l1()` on int8 vectors no longer wraps at 2^31** (upstream [#362](https://github.com/asg017/sqlite-vec/issues/362), ports upstream PR [#365](https://github.com/asg017/sqlite-vec/pull/365) by flysheep-ai) - the sum is 64-bit and the NEON kernel is only used within its 32-bit range; vec0 columns were never affected
- **Vector column types must match exactly** (ports upstream PR [#310](https://github.com/asg017/sqlite-vec/pull/310) by stumpylog) - `float16[4]`, `floaty[4]` and `bitcoin[8]` were accepted as `float` and `bit` by a prefix match; `float32` stays accepted. Any other name followed by `[` is an error (`could not parse vector column`), so a definition like `v float64[2]` cannot fall through to the metadata parser and reopen as a different column kind; tables created with such a name under the old prefix match must be recreated with `float`
- **`make cli` compiles sqlite-vec.c with `-O3`** (upstream [#290](https://github.com/asg017/sqlite-vec/issues/290), after PR [#292](https://github.com/asg017/sqlite-vec/pull/292) by yurivict) - the CLI's copy of the extension was built with no optimisation flag at all; user `CFLAGS` now also reach the vendored `sqlite3.c` and `shell.c` builds, and `-O3` precedes them so they can be overridden
- **`make sqlite-vec.h` on FreeBSD** (upstream [#286](https://github.com/asg017/sqlite-vec/issues/286), after PR [#282](https://github.com/asg017/sqlite-vec/pull/282) by lin72h) - the version parts are computed by Make, not by shell assignments that FreeBSD's `/bin/sh` expands before setting, and the recipe fails if a version macro comes out blank
- **CI builds a 64-bit `linux-aarch64` artifact** - the cross-compile job used `arm-linux-gnueabihf-gcc`, a 32-bit ARM compiler, so the artifact labelled aarch64 was 32-bit (upstream fixed the same job in asg017/sqlite-vec@cc7c29e)
- **CI Android builds are 16KB page aligned** - the Android job never passed the `-Wl,-z,max-page-size=16384` link flag that the fork added support for in v0.2.3-alpha, and now uses NDK 29 (after PR [#249](https://github.com/asg017/sqlite-vec/pull/249) by DarkJoker360)
- **Licence identifiers** (upstream asg017/sqlite-vec@5778fec) - `sqlite-dist.toml` said `MIT OR Apache`, which is not a valid SPDX expression, and the Rust crate and its template used the deprecated `MIT/Apache-2.0` form
- **NEON kernel loop bounds no longer form a pointer before the buffer** - `while (p < end - 63)` style conditions computed an out-of-range pointer for short inputs (16-element int8 L1 and cosine, 16-byte Hamming), which is undefined behaviour even though it was never dereferenced; they now compare remaining lengths. Unaffected inputs run exactly the same iterations

### Added

- **Double-quoted column names in `CREATE VIRTUAL TABLE ... USING vec0(...)`** (upstream [#170](https://github.com/asg017/sqlite-vec/issues/170), after PR [#296](https://github.com/asg017/sqlite-vec/pull/296) by garnacho) - `"my vec" float[2]`, `"order" integer` or `+"the note" text` are accepted for every column kind, so reserved words and names with spaces work as they do in SQLite; a quote inside the name (`"a""b"`), an empty `""` and an unterminated quote are rejected

### Changed

- **AVX kernels are chosen at run time** (upstream [#302](https://github.com/asg017/sqlite-vec/issues/302), after PR [#307](https://github.com/asg017/sqlite-vec/pull/307) by stumpylog) - the AVX L2 and AVX2 Hamming kernels are compiled with per-function target attributes and used only when the running CPU supports them (`__builtin_cpu_supports` on GCC and Clang, `__cpuid` and `_xgetbv` on MSVC), instead of compiling the whole file with `-mavx -mavx2` and probing the build host. One x86_64 binary now runs on any x86-64 CPU as far as the AVX kernels are concerned, so prebuilt binaries cannot SIGILL on pre-AVX machines for that reason (the native MSVC build still uses `__popcnt64` for bit vectors, which needs POPCNT, a 2008-era feature, as before). `SQLITE_VEC_ENABLE_AVX` is now set for every x86_64 target: Linux builds, the Windows CI build, the Rust binding (`build.rs`) and the Go CGO binding, which all ran scalar code before; the Rust and Go bindings also enable NEON on arm64. On those newly SIMD-enabled targets (and, for the Rust and Go bindings on arm64, the NEON L2, L1, cosine and Hamming kernels), distances can differ from the scalar results in the last significant digits because the kernels sum in a different order, so neighbours whose distances were within rounding of each other can swap places and distance thresholds can include or exclude them
- **npm package installs on Android (Termux)** (after PR [#312](https://github.com/asg017/sqlite-vec/pull/312) by kore4lyf) - `android` is listed in `package.json`'s `os` field

## [0.2.8-alpha] - 2026-10-29

All changes in this release were contributed by MayCXC (Aaron Paterson), several ported from the photostructure fork and also proposed upstream.

### Added

- **KNN filters keep exactly the rows SQLite keeps** ([#12](https://github.com/vlasky/sqlite-vec/pull/12))
  - vec0 declares its columns with types, as R-Tree does, and each filter gives the constraint's value the column's affinity and compares as SQLite does: `n = '5'` matches an integer 5, `n = 5.5` no longer matches 5, every number sorts before any text, and NULL matches nothing
  - Text compares under the constraint's collation (`BINARY`, `NOCASE` or `RTRIM`; any other is an error) and, in a UTF-16 database, in the order SQLite's BINARY collation uses there. `t < ?` bound to NULL no longer crashes, and comparisons with a text of exactly 12 bytes no longer fail with "Could not filter metadata fields"
  - `LIKE` and `GLOB` match as SQLite's built-in functions do, honour `PRAGMA case_sensitive_like`, and are 2 to 15x faster, as are text ranges; `rowid in (...)` and text id lookups take values as SQLite's own lookups do
  - `!=` and `IS NOT` under `NOCASE` or `RTRIM`, and `LIKE` and `GLOB`, are checked again by SQLite after the k nearest rows are chosen, so such a query can return fewer than `k` rows. See the metadata section of the vec0 documentation for this and the other documented limits
  - `PRAGMA table_xinfo` on a vec0 table now reports column types
- **A KNN query's vector, `k` and `mmr_lambda` can come from a joined table** ([#14](https://github.com/vlasky/sqlite-vec/pull/14))
  - `select ... from requests r join v on v.embedding match r.q and v.k = r.n` runs one KNN per request row; `k in (2, 3)` and expressions such as `k = w.n + 0` work too
  - `xBestIndex` refuses a plan in which another table would have to supply an argument after vec0 is scanned, so SQLite picks a join order that supplies it. That refusal needs SQLite 3.26.0 or later; older libraries keep the plans they had
  - A cycle, where the table supplying the argument itself reads vec0, now fails with "no query solution" instead of silently returning nothing
  - A lookup join's result is plan dependent: after `ANALYZE` SQLite may run the KNN once per joined row, so a global k needs the KNN in a subquery or CTE. See ARCHITECTURE.md
- **NEON cosine distance for float and int8 vectors** ([#20](https://github.com/vlasky/sqlite-vec/pull/20)) - ports upstream's kernels with double accumulation, about 3x faster for float and 5x for int8 on Apple Silicon, identical results to the scalar loops for every tested input
- **NEON on Linux arm64** ([#21](https://github.com/vlasky/sqlite-vec/pull/21))
  - The Makefile enables NEON when the compiler targets aarch64 Linux, and the NEON code now compiles with GCC. `OMIT_SIMD=1` still builds the scalar version
  - A 100,000-row `float[768]` KNN query takes about 33 ms instead of 77 ms with GCC 14. Float L2 distances can differ from earlier Linux arm64 builds in the last digits, as they already did on macOS arm64, so rows with nearly equal distances may change order
  - A new CI job runs the test suite on `ubuntu-24.04-arm`

### Changed

- **Full scans read vectors through one blob handle per chunk** ([#17](https://github.com/vlasky/sqlite-vec/pull/17)) - `select ... from v` without a MATCH opened and closed a blob per row; a file-backed 10,000-row `float[768]` scan now takes about 12 ms instead of 760 ms. Each row's position is still looked up when it is read, so a row deleted or moved during the scan reports an error or its new vector rather than stale data
- **Each chunk's k nearest rows are selected with a heap** ([#18](https://github.com/vlasky/sqlite-vec/pull/18)) instead of k passes over the chunk's distances; same rows and order as before, with a NaN distance ranking last across chunks as it already did within one
- **Integer metadata `in (...)` lists are binary-searched** ([#10](https://github.com/vlasky/sqlite-vec/pull/10)) - a 10,000-value list on 100,000 rows takes 6.5 ms instead of 322 ms
- **MMR reranking keeps each candidate's similarity to the selection as a running maximum** ([#11](https://github.com/vlasky/sqlite-vec/pull/11)) - identical results, about 25x less distance work for `k = 50`
- **A chunk's vectors are not read when the KNN filters keep none of its rows** ([#13](https://github.com/vlasky/sqlite-vec/pull/13)) - a filtered KNN over 120,000 vectors in 130 chunks runs in about 60 ms instead of 105 ms
- **DELETE reads the chunk's validity bitmap through the handle it already holds** ([#26](https://github.com/vlasky/sqlite-vec/pull/26)), and only when the row's byte went to zero, about 8% fewer instructions per DELETE. A chunk that looked empty is checked once more before it is reclaimed, since a trigger on a shadow table can refill it during the DELETE

### Fixed

- **Static blobs: a heap overflow and three leaks** ([#19](https://github.com/vlasky/sqlite-vec/pull/19))
  - A `vec_static_blob_entries` KNN over a blob whose vector count is a multiple of 8 read one byte past its candidate bitmap
  - Registered blob names, a query's KNN results, and the results of a cursor filtered again without being closed (the inner loop of a join) were never freed
- **Embedded NUL bytes in a text `IN (...)` value read past the copied value** (with [#12](https://github.com/vlasky/sqlite-vec/pull/12))
- **`rowid in (...)` on KNN queries with rowids far apart** ([#9](https://github.com/vlasky/sqlite-vec/pull/9)) - the comparator returned the `int` truncation of an `i64` difference, so rowids exactly 2^32 apart compared equal (a row not in the list matched) and larger differences changed sign, leaving the sorted list out of order and missing rows that were in it
- **`vec_distance_l2()` on int8 vectors of 33,026 or more elements returned NULL on NEON builds** (with [#21](https://github.com/vlasky/sqlite-vec/pull/21)) - the kernel summed the squares in 32 bits; it now sums in 64 bits. `vec0` tables, limited to 8,192 dimensions, were not affected
- **DELETE accepted a row whose validity bit was already clear** ([#25](https://github.com/vlasky/sqlite-vec/pull/25)) - the check tested every higher bit in the same byte as well as the row's own; only a damaged `_chunks` table can produce such a row
- **`make cli` failed to link with GNU ld** ([#22](https://github.com/vlasky/sqlite-vec/pull/22)) - `-ldl -lm` came before the archives that need them
- **Static builds with MSVC failed on `SQLITE_VEC_API`** ([#24](https://github.com/vlasky/sqlite-vec/pull/24)) - the header applied a GCC visibility attribute on every compiler; it is now applied only under GCC and Clang outside Windows
- **Unused-parameter warnings under `SQLITE_CORE`** ([#23](https://github.com/vlasky/sqlite-vec/pull/23)) - the init functions' `pApi` is marked unused when the file is compiled into an application

## [0.2.7-alpha] - 2026-10-05

### Fixed

- **Cosine distance returned ±Inf, NULL or a wrong value for very small or very large nonzero float32 vectors** (upstream [#324](https://github.com/asg017/sqlite-vec/issues/324))
  - Squared magnitudes were accumulated in float32, so elements below roughly 3e-23 underflowed to a zero magnitude and elements above roughly 2e19 overflowed to Inf (giving a distance of 1.0 whatever the direction). In a cosine `vec0` table the affected rows ranked ahead of (or behind) the true nearest neighbours
  - `vec_distance_cosine()`, cosine KNN queries and MMR reranking now accumulate in double precision, as does `vec_normalize()`, which returned NULL, a zero vector or a non-unit vector for the same inputs
  - Cosine distances of ordinary float32 vectors can differ from previous releases in the last few significant digits, as they are now correctly rounded
- **`NPY_MAGIC` initialiser no longer relies on dropping the string terminator** (upstream [#321](https://github.com/asg017/sqlite-vec/issues/321)) - fixes `-Wunterminated-string-initialization` on newer GCC and Clang, and a hard error when compiled as C++

### Changed

- **`xShadowName` now reports `vector_chunksNN` tables** (upstream [#320](https://github.com/asg017/sqlite-vec/issues/320)) - a partial improvement, not a complete fix
  - SQLite matches a newly created table to its virtual table by splitting the name at the last underscore, which the `vector_chunksNN` suffix defeats, so SQLite only learns that these are shadow tables in the cases below
  - SQLite 3.37 to 3.53: they are listed as `shadow` by `PRAGMA table_list`, and write-protected under `SQLITE_DBCONFIG_DEFENSIVE`, only once the database has been VACUUMed. A vec0 table created after that VACUUM is not covered until the next one
  - SQLite 3.54 (unreleased at the time of writing) is expected to recognise them without a VACUUM, once the vec0 table has been used in a connection, though still not in the connection that created the table
  - Once they are recognised, scripts that write to or drop a `vector_chunksNN` table directly are refused in defensive mode, as they already are for the other backing tables
  - Tools should keep identifying vec0 backing tables by name instead of relying on `type = 'shadow'`

## [0.2.6-alpha] - 2026-08-22

### Added

- **INSERT OR REPLACE support for vec0 tables** (ports [asg017/sqlite-vec@b95c05b](https://github.com/asg017/sqlite-vec/commit/b95c05b), upstream [#127](https://github.com/asg017/sqlite-vec/issues/127))
  - Upserts now work with both integer rowids and text primary keys, replacing vectors, metadata, and auxiliary values
- **Empty-chunk reclamation on DELETE** (ports [asg017/sqlite-vec@cb147c8](https://github.com/asg017/sqlite-vec/commit/cb147c8), upstream [#268](https://github.com/asg017/sqlite-vec/issues/268))
  - Deleting the last row of a chunk now removes the chunk and its vector/metadata shadow rows immediately, returning disk space without a manual `optimize`
  - Fixes a shadow-table quirk where the internal SQLite rowid could diverge from the user rowid after chunk delete/recreate cycles, breaking blob lookups
- **NEON and AVX2 SIMD Hamming distance** (ports [asg017/sqlite-vec@d684178](https://github.com/asg017/sqlite-vec/commit/d684178))
  - Bit-vector distance uses NEON `vcnt` at 128+ dimensions and AVX2 VPSHUFB popcount at 256+ dimensions
  - Hardened beyond upstream: AVX2 code requires `__AVX2__` and the Makefile probes the host CPU (`sysctl hw.optional.avx2_0`), so pre-2013 Intel Macs without AVX2 still build and run correctly
- **libFuzzer targets and nightly fuzz CI** (ports upstream fuzz infrastructure)
  - 12 fuzz targets covering vector parsing, vec0 operations, scalar functions, metadata columns, shadow-table corruption, and delete completeness
  - GitHub Actions workflow runs all targets under ASan+UBSan on push to main and nightly

### Fixed

Found by this fork's own first fuzzing runs:

- **Use-after-free in vec0 constructor parsing** - 21 token-scanner guards used `&&` where `||` was intended, so truncated or garbled column definitions could read stale token state pointing at freed memory
- **Signed integer overflow in JSON number parsing** - exponents like `1e440444444` overflowed the parser's int accumulator; now clamped and rejected as out of range
- **`vec_npy_each` hang and buffer over-read** - numpy headers missing mandatory keys left the element count uninitialized, iterating effectively unbounded rows (a 14-byte input hung for 29 minutes), and a `"False"` comparison could read past the end of the header buffer

Ports the applicable correctness fixes from upstream v0.1.8 through v0.1.10, most found by upstream's fuzzing suite:

- **Wrong L2 distances for int8 vectors on ARM NEON builds** ([asg017/sqlite-vec@7de925b](https://github.com/asg017/sqlite-vec/commit/7de925b)) - an int16 overflow in the NEON distance loop produced NaN or wrong results for element differences above 181; the default Apple Silicon build was affected
- **DELETE on long text metadata** ([asg017/sqlite-vec@ee9bd2b](https://github.com/asg017/sqlite-vec/commit/ee9bd2b)) - metadata-clear errors were silently swallowed, and the long-text path returned a status the caller would have treated as an error
- **NaN and Inf elements now rejected in float32 vector input** ([asg017/sqlite-vec@c4c23bd](https://github.com/asg017/sqlite-vec/commit/c4c23bd)) - NaN elements break KNN ordering invariants
- **Undefined behaviour fixes** ([asg017/sqlite-vec@cdbc347](https://github.com/asg017/sqlite-vec/commit/cdbc347), [@2f4c2e4](https://github.com/asg017/sqlite-vec/commit/2f4c2e4), [@1b53b94](https://github.com/asg017/sqlite-vec/commit/1b53b94)) - unaligned float/u64 loads from blobs, a one-past-end read in the numpy header tokenizer, an out-of-range float-to-int8 conversion in `vec_quantize_int8` (now clamped, NaN-safe), and an ABI-incompatible cleanup function pointer

### Changed

- SIMD flags are no longer added when cross-compiling for Android (`CC` containing "android")
- Removed dead typedef macros inherited from sqlite3.c

## [0.2.5-alpha] - 2026-08-22

### Added

- **MMR (Maximal Marginal Relevance) reranking for KNN queries** ([#6](https://github.com/vlasky/sqlite-vec/pull/6), rebased from [asg017/sqlite-vec#267](https://github.com/asg017/sqlite-vec/pull/267))
  - New hidden `mmr_lambda` column on vec0 tables: `SELECT rowid, distance FROM v WHERE embedding MATCH ? AND k = 10 AND mmr_lambda = 0.5`
  - `mmr_lambda` balances relevance against diversity (1.0 = pure relevance, 0.0 = maximum diversity)
  - Diversity term is normalized for consistent behaviour across all distance metrics
  - Includes pytest + syrupy snapshot tests

### Fixed

- **Memory leaks in vec0 operations and error paths** ([#7](https://github.com/vlasky/sqlite-vec/issues/7), ports [asg017/sqlite-vec#258](https://github.com/asg017/sqlite-vec/pull/258))
  - Freed column names and shadow-table names for partition, auxiliary, and metadata columns on table close
  - Freed SQL strings, statements, blob handles, and KNN buffers on error paths across insert, update, delete, and query code
  - Freed column names copied into the vtab when a constructor parse fails midway
  - Verified with macOS `leaks(1)`: 17 leaks (1,168 bytes) before, 0 after, on a workload exercising all affected paths
- **NaN results from cosine distance on zero-magnitude vectors** ([#8](https://github.com/vlasky/sqlite-vec/issues/8))
  - `vec_distance_cosine()` now returns NULL when either input has zero magnitude (float, int8, and bit vectors)
  - `vec_normalize()` now returns NULL for a zero vector instead of a vector of NaNs
  - vec0 tables with `distance_metric=cosine` now reject zero-magnitude vectors at INSERT and UPDATE time, and reject zero-magnitude query vectors in KNN queries, so NaN can never corrupt KNN orderings (behaviour change: such inserts previously succeeded silently)
- **Wrong pointer passed to cleanup in `ensure_vector_match` error path** ([#3](https://github.com/vlasky/sqlite-vec/pull/3))
- **Removed duplicate Rust package from repo root** ([#4](https://github.com/vlasky/sqlite-vec/issues/4)) - `cargo add` from this git repository now resolves the single crate in `bindings/rust/`

### Documentation

- Fixed errors in Ruby documentation examples
- Documented the exclusive database access requirement for `optimize` and `VACUUM`

## [0.2.4-alpha] - 2026-01-03

### Added

- **Lua binding with IEEE 754 compliant float serialization** ([#237](https://github.com/asg017/sqlite-vec/pull/237))
  - `bindings/lua/sqlite_vec.lua` provides `load()`, `serialize_f32()`, and `serialize_json()` functions
  - Lua 5.1+ compatible with lsqlite3
  - IEEE 754 single-precision float encoding with round-half-to-even (banker's rounding)
  - Proper handling of special values: NaN, Inf, -Inf, -0.0, subnormals
  - Example script and runner in `/examples/simple-lua/`

## [0.2.3-alpha] - 2025-12-29

### Added

- **Android 16KB page support** ([#254](https://github.com/asg017/sqlite-vec/pull/254))
  - Added `LDFLAGS` support to Makefile for passing linker-specific flags
  - Enables Android 15+ compatibility via `-Wl,-z,max-page-size=16384`
  - Required for Play Store app submissions on devices with 16KB memory pages

- **Improved shared library build and installation** ([#149](https://github.com/asg017/sqlite-vec/issues/149))
  - Configurable install paths via `INSTALL_PREFIX`, `INSTALL_LIB_DIR`, `INSTALL_INCLUDE_DIR`, `INSTALL_BIN_DIR`
  - Hidden internal symbols with `-fvisibility=hidden`, exposing only public API
  - `EXT_CFLAGS` captures user-provided `CFLAGS` and `CPPFLAGS`

- **Optimize/VACUUM integration test and documentation**
  - Added test demonstrating optimize command with VACUUM for full space reclamation

### Fixed

- **Linux linking error with libm** ([#252](https://github.com/asg017/sqlite-vec/pull/252))
  - Moved `-lm` flag from `CFLAGS` to `LDLIBS` at end of linker command
  - Fixes "undefined symbol: sqrtf" errors on some Linux distributions
  - Linker now correctly resolves math library symbols

### Documentation

- **Fixed incomplete KNN and Matryoshka guides** ([#208](https://github.com/asg017/sqlite-vec/pull/208), [#209](https://github.com/asg017/sqlite-vec/pull/209))
  - Completed unfinished sentence describing manual KNN method trade-offs
  - Added paper citation and Matryoshka naming explanation

## [0.2.2-alpha] - 2025-12-02

### Added

- **GLOB operator for text metadata columns** ([#191](https://github.com/asg017/sqlite-vec/issues/191))
  - Standard SQL pattern matching with `*` (any characters) and `?` (single character) wildcards
  - Case-sensitive matching (unlike LIKE)
  - Fast path optimization for prefix-only patterns (e.g., `'prefix*'`)
  - Full pattern matching with `sqlite3_strglob()` for complex patterns

- **IS/IS NOT/IS NULL/IS NOT NULL operators for metadata columns** ([#190](https://github.com/asg017/sqlite-vec/issues/190))
  - **Note**: sqlite-vec metadata columns do not currently support NULL values. These operators provide syntactic compatibility within this limitation.
  - `IS` behaves like `=` (all metadata values are non-NULL)
  - `IS NOT` behaves like `!=` (all metadata values are non-NULL)
  - `IS NULL` always returns false (no NULL values exist in metadata)
  - `IS NOT NULL` always returns true (all metadata values are non-NULL)
  - Works on all metadata types: INTEGER, FLOAT, TEXT, and BOOLEAN

### Fixed

- **All compilation warnings eliminated**
  - Fixed critical logic bug: `metadataInIdx` type corrected from `size_t` to `int` (prevented -1 wrapping to SIZE_MAX)
  - Fixed 5 sign comparison warnings with proper type casts
  - Fixed 7 uninitialized variable warnings by adding initializers and default cases
  - Clean compilation with `-Wall -Wextra` (zero warnings)

## [0.2.1-alpha] - 2025-12-02

### Added

- **LIKE operator for text metadata columns** ([#197](https://github.com/asg017/sqlite-vec/issues/197))
  - Standard SQL pattern matching with `%` and `_` wildcards
  - Case-insensitive matching (SQLite default)

### Fixed

- **Locale-dependent JSON parsing** ([#241](https://github.com/asg017/sqlite-vec/issues/241))
  - Custom locale-independent float parser fixes JSON parsing in non-C locales
  - No platform dependencies, thread-safe

- **musl libc compilation** (Alpine Linux)
  - Removed non-portable preprocessor macros from vendored sqlite3.c

## [0.2.0-alpha] - 2025-11-28

### Added

- **Distance constraints for KNN queries** ([#166](https://github.com/asg017/sqlite-vec/pull/166))
  - Support GT, GE, LT, LE operators on the `distance` column in KNN queries
  - Enables cursor-based pagination: `WHERE embedding MATCH ? AND k = 10 AND distance > 0.5`
  - Enables range queries: `WHERE embedding MATCH ? AND k = 100 AND distance BETWEEN 0.5 AND 1.0`
  - Works with all vector types (float32, int8, bit)
  - Compatible with partition keys, metadata, and auxiliary columns
  - Comprehensive test coverage (15 tests)
  - Fixed variable shadowing issues from original PR
  - Documented precision handling and pagination caveats

- **Optimize command for space reclamation** ([#210](https://github.com/asg017/sqlite-vec/pull/210))
  - New special command: `INSERT INTO vec_table(vec_table) VALUES('optimize')`
  - Reclaims disk space after DELETE operations by compacting shadow tables
  - Rebuilds vector chunks with only valid rows
  - Updates rowid mappings to maintain data integrity

- **Cosine distance support for binary vectors** ([#212](https://github.com/asg017/sqlite-vec/pull/212))
  - Added `distance_cosine_bit()` function for binary quantized vectors
  - Enables cosine similarity metric on bit-packed vectors
  - Useful for memory-efficient semantic search

- **ALTER TABLE RENAME support** ([#203](https://github.com/asg017/sqlite-vec/pull/203))
  - Implement `vec0Rename()` callback for virtual table module
  - Allows renaming vec0 tables with standard SQL: `ALTER TABLE old_name RENAME TO new_name`
  - Properly renames all shadow tables and internal metadata

- **Language bindings and package configurations for GitHub installation**
  - Go CGO bindings (`bindings/go/cgo/`) with `Auto()` and serialization helpers
  - Python package configuration (`pyproject.toml`, `setup.py`) for `pip install git+...`
  - Node.js package configuration (`package.json`) for `npm install vlasky/sqlite-vec`
  - Ruby gem configuration (`sqlite-vec.gemspec`) for `gem install` from git
  - Rust crate configuration (`Cargo.toml`, `src/lib.rs`) for `cargo add --git`
  - All packages support installing from main branch or specific version tags
  - Documentation in README with installation table for all languages

- **Python loadable extension support documentation**
  - Added note about Python requiring `--enable-loadable-sqlite-extensions` build flag
  - Recommended using `uv` for virtual environments (uses system Python with extension support)
  - Documented workarounds for pyenv and custom Python builds

### Fixed

- **Memory leak on DELETE operations** ([#243](https://github.com/asg017/sqlite-vec/pull/243))
  - Added `vec0Update_Delete_ClearRowid()` to clear deleted rowids
  - Added `vec0Update_Delete_ClearVectors()` to clear deleted vector data
  - Prevents memory accumulation from deleted rows
  - Vectors and rowids now properly zeroed out on deletion

- **CI/CD build infrastructure** ([#228](https://github.com/asg017/sqlite-vec/pull/228))
  - Upgraded deprecated ubuntu-20.04 runners to ubuntu-latest
  - Added native ARM64 builds using ubuntu-24.04-arm
  - Removed cross-compilation dependencies (gcc-aarch64-linux-gnu)
  - Fixed macOS link flags for undefined symbols

## Original Version

This fork is based on [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) v0.1.7-alpha.2.

All features and functionality from the original repository are preserved.
See the [original documentation](https://alexgarcia.xyz/sqlite-vec/) for complete usage information.

---

## Notes

This is a community-maintained fork created to merge pending upstream PRs and provide
continued support while the original author is unavailable. Once development resumes
on the original repository, users are encouraged to switch back.

All original implementation credit goes to [Alex Garcia](https://github.com/asg017).
