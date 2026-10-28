use probe::{joined, read_location};
fn main() {
    println!("{}\n{}", origin::same_file!(), origin::cross_file!(first));
}
