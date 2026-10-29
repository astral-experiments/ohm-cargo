extern crate proc_macro;
#[proc_macro]
pub fn answer_from_manifest(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let manifest = std::path::PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").unwrap()).join("Cargo.toml");
    let source = std::fs::read(manifest).unwrap();
    let needle = b"\ntest = false\n";
    if source.windows(needle.len()).any(|bytes| bytes == needle) { "17u8" } else { "29u8" }.parse().unwrap()
}
