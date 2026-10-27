extern crate proc_macro;
use proc_macro::TokenStream;
#[proc_macro_derive(Marker)]
pub fn marker(_: TokenStream) -> TokenStream {
    let _ = proc_macro::Literal::u8_unsuffixed(0);
    TokenStream::new()
}
#[proc_macro]
pub fn report(t: TokenStream) -> TokenStream {
    let span = t.into_iter().next().unwrap().span();
    let text = format!("{:?}", span);
    TokenStream::from(proc_macro::TokenTree::Literal(proc_macro::Literal::string(&text)))
}
