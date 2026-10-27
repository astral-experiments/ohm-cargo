#[derive(Default)]
struct Conflicts(HashSet<(Ident, Ident)>);
impl Conflicts {
    fn insert(&mut self, a: Ident, b: Ident) {
        if a < b {
            self.0.insert((a, b));
        } else {
            self.0.insert((b, a));
        }
    }

    fn to_tokens(&self, struct_error: &StructError) -> Result<TokenStream> {
        self.0
            .iter()
            .map(|(a, b)| {
                let af = Formattable::display(&a);
                let bf = Formattable::display(&b);

                let error_a_to_b = struct_error
                    .conflict()
                    .format(hash!("first" => af, "second" => bf))?;

                let error_b_to_a = struct_error
                    .conflict()
                    .format(hash!("first" => bf, "second" => af))?;

                Ok(quote! {
                    # use ::attribute_derive::__private::proc_macro2;
                    # use ::attribute_derive::__private::syn::{Error, Spanned};
                    if let (Some(__a), Some(__b)) = (&__partial.#a, &__partial.#b) {
                        if let Some(__joined_span) = __a.error_span().join(__b.error_span()) {
                            return Err(Error::new(__joined_span, #error_a_to_b));
                        } else {
                            let mut __error = Error::new(__a.error_span(), #error_a_to_b);
                            __error.combine(Error::new(__b.error_span(), #error_b_to_a));
                            return Err(__error);
                        }
                    }
                })
            })
            .collect()
    }
}
