use ruff_python_ast::Expr;
use ruff_python_parser::parse_module;

fn main() {
    assert!(parse_module("match value:\n    case -1: pass\n").is_ok());
    assert!(parse_module("answer = [\n").is_err());
    let result = parse_module("match value:\n    case -1**2: pass\n");
    let status = if result.is_ok() { "accepted" } else { "rejected" };
    println!("Expr={} signed-expression={status}", std::mem::size_of::<Expr>());
}
