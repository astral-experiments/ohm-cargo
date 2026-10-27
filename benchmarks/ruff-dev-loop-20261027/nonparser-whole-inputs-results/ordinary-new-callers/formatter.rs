use ruff_python_formatter::{format_module_source, PyFormatOptions};
fn main() {
    let formatted = format_module_source("#\tTabbed\npass #\tTabbed\n", PyFormatOptions::default()).unwrap();
    print!("{}", formatted.as_code());
}
