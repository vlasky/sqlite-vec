fn main() {
    let root = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("../..");

    cc::Build::new()
        .file(root.join("sqlite-vec.c"))
        .include(&root)
        .include(root.join("vendor"))
        .compile("sqlite_vec0");
}
