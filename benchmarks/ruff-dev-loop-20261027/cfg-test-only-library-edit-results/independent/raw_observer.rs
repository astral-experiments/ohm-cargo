#![feature(proc_macro_tracked_path)]
extern crate proc_macro; use proc_macro::TokenStream; #[proc_macro] pub fn measure_source(_:TokenStream)->TokenStream {let p="/home/dev-user/code/oss/ruff-ohm-whole-native-20261027/crates/ty_ide/src/docstring.rs"; proc_macro::tracked::path(p); std::fs::metadata(p).unwrap().len().to_string().parse().unwrap()}
