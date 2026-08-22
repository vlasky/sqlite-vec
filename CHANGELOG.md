# Changelog

All notable changes to this community fork will be documented in this file.

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
