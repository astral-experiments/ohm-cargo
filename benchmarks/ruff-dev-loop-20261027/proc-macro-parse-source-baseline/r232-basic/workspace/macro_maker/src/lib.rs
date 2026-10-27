extern crate proc_macro;
use proc_macro::TokenStream;
#[proc_macro_derive(Marker)]
pub fn marker(_: TokenStream) -> TokenStream {
    let _: TokenStream = "0".parse().unwrap();
    TokenStream::new()
}
