extern crate proc_macro;
#[proc_macro]
pub fn check_invocation(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
    if std::env::args_os().any(|arg| arg == "emit-rlink" || arg == "-Zemit-rlink") {
        "17u8".parse().unwrap()
    } else {
        "compile_error!(\"link recipe was not requested\")".parse().unwrap()
    }
}
