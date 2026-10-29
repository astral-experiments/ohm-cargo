extern crate ruff_db;
extern crate ruff_python_parser;

pub fn check_real_library(input: &str) -> bool {
    let _ = std::hint::black_box(ruff_db::parsed::parsed_string_annotation);
    ruff_python_parser::parse_module(input).is_ok()
}
