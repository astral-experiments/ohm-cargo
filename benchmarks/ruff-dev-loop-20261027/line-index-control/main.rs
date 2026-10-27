use ruff_source_file::{LineIndex, OneIndexed, SourceCode};

fn main() {
    for text in ["a\nb", "a\r\nb", "a\rb"] {
        let index = LineIndex::from_source_text(text);
        let end = SourceCode::new(text, &index).line_end_exclusive(OneIndexed::from_zero_indexed(0));
        println!("{}", end.to_usize());
    }
}
