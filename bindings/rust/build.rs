fn main() {
    let root = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("../..");

    let mut build = cc::Build::new();
    build
        .file(root.join("sqlite-vec.c"))
        .include(&root)
        .include(root.join("vendor"));

    // The same SIMD kernels the Makefile enables. The AVX kernels check the
    // running CPU before they are used, so this is safe on any x86-64 target;
    // NEON is part of the AArch64 baseline.
    let arch = std::env::var("CARGO_CFG_TARGET_ARCH").unwrap_or_default();
    let env = std::env::var("CARGO_CFG_TARGET_ENV").unwrap_or_default();
    if arch == "x86_64" {
        build.define("SQLITE_VEC_ENABLE_AVX", None);
    } else if arch == "aarch64" && env != "msvc" {
        build.define("SQLITE_VEC_ENABLE_NEON", None);
    }

    build.compile("sqlite_vec0");
}
