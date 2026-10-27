#[derive(macro_maker::Marker)]
pub struct Marker;
include!("late.rs");
pub fn value() -> u8 { 8 }
const _: &[u8] = include_bytes!("../parse-input.txt");
