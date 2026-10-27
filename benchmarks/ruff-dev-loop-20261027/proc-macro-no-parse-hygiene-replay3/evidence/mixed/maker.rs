extern crate proc_macro;
use proc_macro::{Literal,TokenStream,TokenTree};
#[proc_macro_derive(Marker)]
pub fn marker(_: TokenStream) -> TokenStream { TokenStream::new() }
#[proc_macro]
pub fn report(t: TokenStream) -> TokenStream { let _ = &t; let span = proc_macro::Span::mixed_site(); TokenTree::Literal(Literal::string(&format!("{span:?}"))).into() }
