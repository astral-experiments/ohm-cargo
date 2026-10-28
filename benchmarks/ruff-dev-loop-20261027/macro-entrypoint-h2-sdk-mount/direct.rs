extern crate self as ruff_index;

pub trait Idx {
    fn new(value: usize) -> Self;
    fn index(self) -> usize;
}

#[ruff_macros::newtype_index]
pub struct Slot;

fn main() {
    println!("{}", Slot::MAX.as_u32());
}
