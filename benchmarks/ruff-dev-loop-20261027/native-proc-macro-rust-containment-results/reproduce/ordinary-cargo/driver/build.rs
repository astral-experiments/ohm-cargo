fn main() {
    let object = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()).join("native.o");
    assert!(std::process::Command::new("cc")
        .args(["-fPIC", "-c", "native.c", "-o"])
        .arg(&object)
        .status().unwrap().success());
    println!("cargo:rustc-link-arg={}", object.display());
    println!("cargo:rerun-if-changed=native.c");
}
