#![crate_type = "rlib"]

#[maker::parsed]
#[derive(maker::Parsed, maker::Tracked)]
pub struct Marker;

include!("late.rs");

pub fn value() -> u8 {
    7
}
