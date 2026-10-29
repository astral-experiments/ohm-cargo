extern crate held_bridge;
extern crate ruff_python_parser;

pub fn accepted_by_both(input: &str) -> bool {
    held_bridge::accepts(input) && ruff_python_parser::parse_module(input).is_ok()
}
