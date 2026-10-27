use std::io::{self, Read};
fn main() {
    let mut data = Vec::new();
    io::stdin().read_to_end(&mut data).unwrap();
    print!("{}", blake3::hash(&data));
}
