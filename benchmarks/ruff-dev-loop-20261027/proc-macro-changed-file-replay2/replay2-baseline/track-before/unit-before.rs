#[derive(macro_maker::Marker)]
pub struct Marker;
include!("late.rs");
pub fn value() -> u8 { 7 }
const _: &[u8] = include_bytes!("../parse-input.txt");
