fn main() {
    for input in ["a\rb","a\r\nb","a\u{2028}b","a\u{2029}b"] {
        let value = ruff_formatter::normalize_newlines(input, ['\r','\u{2028}','\u{2029}']);
        println!("{}",value.escape_default());
    }
}
