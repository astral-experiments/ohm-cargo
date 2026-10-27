#![feature(proc_macro_tracked_path)]
extern crate proc_macro;
use proc_macro::{Ident, Literal, Punct, Spacing, Span, TokenStream, TokenTree};
#[proc_macro_derive(Marker)]
pub fn marker(_: TokenStream) -> TokenStream {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../unit/parse-input.txt");
    let text = std::fs::read_to_string(&path).unwrap();
    proc_macro::tracked::path(&path);
    let parsed: TokenStream = text.parse().unwrap();

    let ident = |s| TokenTree::Ident(Ident::new(s, Span::call_site()));
    let punct = |ch| TokenTree::Punct(Punct::new(ch, Spacing::Alone));
    let mut output: TokenStream = [ident("pub"), ident("const"), ident("PARSED_INPUT"), punct(':'), ident("u32"), punct('=')].into_iter().collect();
    output.extend(parsed);
    output.extend([punct(';')]);
    output
}
#[proc_macro]
pub fn report(t: TokenStream) -> TokenStream {
    let span = t.into_iter().next().unwrap().span();
    let text = format!("{:?}", span);
    TokenStream::from(TokenTree::Literal(Literal::string(&text)))
}
