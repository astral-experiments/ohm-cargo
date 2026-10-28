use ruff_formatter::{FormatError, InvalidDocumentError, format_element::tag::TagKind};
fn main() {
    println!("{}", FormatError::PoorLayout);
    println!("{}", FormatError::InvalidDocument(InvalidDocumentError::StartTagMissing { kind: TagKind::Group }));
}
