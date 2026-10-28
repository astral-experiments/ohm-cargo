use probe::{read_location, FieldLocation};
bitflags::bitflags! {
    #[derive(FieldLocation)]
    pub struct Flags: u64 { const ENABLED = 1; }
}
fn main() {
    println!("{}\n{}\n{}", OBSERVED.0, OBSERVED.1, OBSERVED.2);
}
