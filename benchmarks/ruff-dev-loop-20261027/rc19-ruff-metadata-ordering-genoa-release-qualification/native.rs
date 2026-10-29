use ruff_python_trivia::{has_leading_content, indentation_at_offset};
use ruff_source_file::{LineIndex, SourceCode};
use ruff_text_size::TextSize;

fn main() {
    let source = "q\r\n  alpha\n";
    let offset = TextSize::new(5);
    let index = LineIndex::from_source_text(source);
    let file = SourceCode::new(source, &index);
    let indent = indentation_at_offset(offset, source).unwrap();
    println!("{} {} {} {}", file.line_index(offset).get(), indent.len(),
             has_leading_content(offset, source), u32::from(offset));
}
