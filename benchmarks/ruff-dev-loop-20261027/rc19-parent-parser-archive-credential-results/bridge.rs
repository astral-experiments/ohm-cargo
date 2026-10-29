pub use ruff_python_parser::parse_module as parse;

pub fn accepts(input: &str) -> bool {
    parse(input).is_ok()
}
