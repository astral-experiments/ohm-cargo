use std::{env, path::PathBuf};
fn main() {
    let pkg = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let native = pkg.parent().unwrap().parent().unwrap().join("native");
    println!("cargo::rerun-if-changed=build.rs");
    println!("cargo::rerun-if-changed={}", native.join("late/libohm_269_transitive.a").display());
    println!("cargo::rerun-if-changed={}", native.join("early").display());
    for dir in ["early", "late"] {
        println!("cargo::rustc-link-search=native={}", native.join(dir).display());
    }
}
