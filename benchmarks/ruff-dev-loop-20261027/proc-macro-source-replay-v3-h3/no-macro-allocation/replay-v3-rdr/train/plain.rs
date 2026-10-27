#![crate_type="rlib"]
#[inline] pub fn left() -> (&'static str, u32) { ("a long repeated string from the same module", 1) }
#[inline] pub fn right() -> (&'static str, u32) { ("a long repeated string from the same module", 7) }
pub fn observed() -> bool { left().0 == right().0 && right().1 == 8 }
