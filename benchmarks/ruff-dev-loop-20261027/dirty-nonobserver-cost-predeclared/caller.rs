fn main() {
    let range: std::ops::Range<usize> =
        ruff_text_size::TextRange::new(2u32.into(), 6u32.into()).to_std_range();
    assert_eq!(range, 2..6);
    println!("{}-{}", range.start, range.end);
}
