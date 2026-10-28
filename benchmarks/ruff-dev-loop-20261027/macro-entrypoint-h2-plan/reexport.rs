#[ruff_index::newtype_index]
pub struct Slot;

fn main() {
    println!("{}", Slot::MAX.as_u32());
}
