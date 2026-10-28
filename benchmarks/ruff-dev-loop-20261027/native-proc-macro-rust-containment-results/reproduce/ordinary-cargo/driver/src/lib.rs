extern crate proc_macro;
extern "C" {
    fn native_value() -> u32;
}
#[proc_macro_derive(NativeValue)]
pub fn expand(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let value = unsafe { native_value() };
    format!("impl Value {{ const NUMBER: u32 = {value}; }}").parse().unwrap()
}
