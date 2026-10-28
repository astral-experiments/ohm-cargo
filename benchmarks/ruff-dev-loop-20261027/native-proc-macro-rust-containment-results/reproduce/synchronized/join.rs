#![feature(proc_macro_span)]
extern crate proc_macro;
extern "C" {fn selected_literal()->u32;}
#[proc_macro]
pub fn sample(input:proc_macro::TokenStream)->proc_macro::TokenStream {
    let mut tokens=input.into_iter();
    let start=tokens.next().unwrap();
    let end=tokens.next().unwrap();
    assert!(tokens.next().is_none());
    assert!(matches!(start,proc_macro::TokenTree::Punct(ref p) if p.as_char()=='<'));
    assert!(matches!(end,proc_macro::TokenTree::Ident(ref i) if i.to_string()=="Internal"));
    let joined=start.span().join(end.span()).expect("two distinct literal tokens in a single exported rule");
    let ident=proc_macro::Ident::new("wait_value",joined);
    let mut output=proc_macro::TokenStream::from(proc_macro::TokenTree::Ident(ident));
    output.extend(format!("!({})",unsafe{selected_literal()}).parse::<proc_macro::TokenStream>().unwrap());
    output
}
#[proc_macro_derive(Native)]
pub fn native(_:proc_macro::TokenStream)->proc_macro::TokenStream {
    use std::io::Write;
    let n=unsafe{selected_literal()};
    let path=std::path::PathBuf::from(std::env::var_os("OHM_SYNC_DIR").unwrap()).join("actual-derive-calls");
    let mut calls=std::fs::OpenOptions::new().append(true).create(true).open(path).unwrap();
    writeln!(calls,"{}",n).unwrap();
    format!("impl Foo {{ const VALUE: u32 = {n}; }}").parse().unwrap()
}
