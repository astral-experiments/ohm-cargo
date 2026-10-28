#[used]
static MAGIC: [u8; 25] = *b"OHMJ_UNIQUE_FIXTURE_17END";

#[proc_macro]
pub fn hold(tokens: TokenStream) -> TokenStream {
    let _ = Span::call_site().line();  // Prevent replay of this coordinating invocation.
    let observed = if tokens.to_string()=="dso" {
        let bytes = unsafe { [std::ptr::read_volatile(&MAGIC[20]), std::ptr::read_volatile(&MAGIC[21])] };
        String::from_utf8(bytes.to_vec()).unwrap()
    } else {
        let literal = tokens.expand_expr().unwrap().to_string();
        literal.trim_matches('"').to_string()
    };
    assert!(&observed == "17" || &observed == "29", "received {observed:?}");
    let root=std::path::PathBuf::from(std::env::var_os("OHM_JOIN_COORD").unwrap());
    if root.join("armed").is_file() {
        std::fs::write(root.join("observed"),&observed).unwrap();
        let start=std::time::Instant::now();
        while !root.join("release").exists() {
            assert!(start.elapsed().as_secs()<25);
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
    }
    TokenTree::Literal(Literal::string(&observed)).into()
}
