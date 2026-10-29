extern crate proc_macro;
#[proc_macro]
pub fn observed(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let emit = std::env::args_os().any(|arg| arg == "emit-rlink" || arg == "-Zemit-rlink");
    if emit { "17" } else { "29" }.parse().unwrap()
}
