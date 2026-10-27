extern crate proc_macro;
use proc_macro::TokenStream;
#[proc_macro_derive(Marker)]
pub fn marker(_: TokenStream) -> TokenStream {
    let _ = proc_macro::Literal::u8_unsuffixed(0);
    TokenStream::new()
}
