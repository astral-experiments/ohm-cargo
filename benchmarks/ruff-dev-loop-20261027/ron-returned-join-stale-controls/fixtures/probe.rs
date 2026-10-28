#![feature(proc_macro_span)]
extern crate proc_macro;
use proc_macro::{Delimiter, Group, Ident, Literal, Punct, Spacing, Span, TokenStream, TokenTree};

fn encoded(span: Span) -> String {
    let location = format!("{}:{}:{}-{}:{}", span.file(), span.line(), span.column(), span.end().line(), span.end().column());
    #[cfg(measure_absolute)]
    let location = format!("{location} {span:?}");
    location
}

fn forwarded(span: Span) -> TokenStream {
    let name = TokenTree::Ident(Ident::new("read_location", Span::call_site()));
    let bang = TokenTree::Punct(Punct::new('!', Spacing::Alone));
    let body = TokenStream::from(TokenTree::Ident(Ident::new("result", span)));
    let group = TokenTree::Group(Group::new(Delimiter::Parenthesis, body));
    [name, bang, group].into_iter().collect()
}

#[proc_macro]
pub fn read_location(tokens: TokenStream) -> TokenStream {
    let token = tokens.into_iter().next().unwrap();
    TokenTree::Literal(Literal::string(&encoded(token.span()))).into()
}

#[proc_macro]
pub fn joined(tokens: TokenStream) -> TokenStream {
    let mut tokens = tokens.into_iter();
    let lo = tokens.next().unwrap().span();
    let hi = tokens.next().unwrap().span();
    assert!(tokens.next().is_none());
    match lo.join(hi) {
        Some(span) => forwarded(span),
        None => TokenTree::Literal(Literal::string("different-files")).into(),
    }
}

#[proc_macro_derive(FieldLocation)]
pub fn field_location(record: TokenStream) -> TokenStream {
    for token in record {
        if let TokenTree::Group(fields) = token {
            if fields.delimiter() != Delimiter::Parenthesis {
                continue;
            }
            let mut field = fields.stream().into_iter();
            let first = field.next().unwrap();
            let last = field.last().unwrap();
            assert_eq!(first.to_string(), "<");
            assert_eq!(last.to_string(), "Internal");
            let (first, last) = (first.span(), last.span());
            let arguments: TokenStream = [
                TokenTree::Literal(Literal::string(&encoded(first))),
                TokenTree::Punct(Punct::new(',', Spacing::Alone)),
                TokenTree::Literal(Literal::string(&encoded(last))),
                TokenTree::Punct(Punct::new(',', Spacing::Alone)),
            ].into_iter().collect();
            let mut tuple = arguments;
            tuple.extend(forwarded(first.join(last).expect("expected one source file")));
            let mut rhs: TokenStream = "pub const OBSERVED: (&str, &str, &str) =".parse().unwrap();
            rhs.extend([TokenTree::Group(Group::new(Delimiter::Parenthesis, tuple))]);
            rhs.extend(";".parse::<TokenStream>().unwrap());
            return rhs;
        }
    }
    panic!("no tuple field in bitflags output")
}
