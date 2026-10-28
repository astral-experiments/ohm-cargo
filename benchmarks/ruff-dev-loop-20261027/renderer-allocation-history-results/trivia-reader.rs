use ruff_python_trivia::{expand_tabs, tab_offset};
use std::borrow::Cow;
fn main() {
    assert!(matches!(expand_tabs("unchanged"), Cow::Borrowed(_)));
    assert!(matches!(expand_tabs("  \tvalue"), Cow::Owned(_)));
    assert_eq!(expand_tabs("  \tvalue"), "        value");
    assert_eq!(tab_offset(2, 8), 6);
    println!("3 expansion checks, tab delta 6");
}
