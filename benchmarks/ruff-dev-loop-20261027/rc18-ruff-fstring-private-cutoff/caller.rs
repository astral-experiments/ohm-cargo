fn main() {
    for source in [
        r#"f"{x}abc""#,
        r#"f"" f"{x}""#,
        r#"f"{'x':.0}""#,
        r#"f"{x > y}""#,
    ] {
        let expression = ruff_python_parser::parse_expression(source).unwrap();
        let truthiness = ruff_python_ast::helpers::Truthiness::from_expr(expression.expr(), |_| false);
        println!("{truthiness:?}");
    }
}
