fn main() {
    let input = "from x import (*)\n";
    match ruff_python_parser::parse_module(input) {
        Ok(_) => println!("accepted"),
        Err(error) => println!("rejected: {}", error.error),
    }
}
