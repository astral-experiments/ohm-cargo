use ruff_linter::linter::{lint_only, ParseSource};
use ruff_linter::registry::Rule;
use ruff_linter::settings::{flags::Noqa, LinterSettings};
use ruff_linter::source_kind::SourceKind;
use ruff_python_ast::PySourceType;
use std::io::{self, BufRead};
use std::path::Path;

fn main() {
    let settings = LinterSettings::for_rule(Rule::ExprOrTrue);
    for (index, input) in io::stdin().lock().lines().enumerate() {
        let source = SourceKind::Python { code: input.unwrap() + "\n", is_stub: false };
        let outcome = lint_only(
            Path::new("fstring.py"), None, &settings, Noqa::Disabled, &source,
            PySourceType::Python, ParseSource::None,
        );
        assert!(!outcome.has_invalid_syntax());
        match outcome.diagnostics.len() {
            0 => {}
            1 => println!("{} SIM222", index + 1),
            _ => panic!("unexpected diagnostic count"),
        }
    }
}
