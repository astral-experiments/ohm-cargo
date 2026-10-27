extern crate proc_macro;
#[proc_macro]
pub fn native_offset(input:proc_macro::TokenStream)->proc_macro::TokenStream{
    let marker=input.into_iter().next().unwrap().span();
    format!("{:?}",format!("{marker:?}")).parse().unwrap()
}
