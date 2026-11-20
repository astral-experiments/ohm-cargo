use std::fmt::Write as _;

use proc_macro2::{TokenStream, TokenTree};
use serde::Deserialize;

#[derive(Deserialize)]
struct Extraction {
    format_version: u32,
    doctests: Vec<Example>,
}

#[derive(Deserialize)]
struct Example {
    name: String,
    file: String,
    line: usize,
    doctest_attributes: Attributes,
    doctest_code: Option<Code>,
    original_code: String,
}

impl Example {
    /// Ignored standalone cases are listed by the driver but have no module in the bundle.
    fn standalone(&self) -> bool {
        let attrs = &self.doctest_attributes;
        self.doctest_code.is_none()
            || attrs.standalone_crate
            || attrs.test_harness
            || attrs.compile_fail
    }
}

#[derive(Deserialize)]
struct Attributes {
    ignore: Ignore,
    should_panic: bool,
    no_run: bool,
    compile_fail: bool,
    standalone_crate: bool,
    test_harness: bool,
    edition: Option<String>,
    error_codes: Vec<String>,
    unknown: Vec<String>,
}

#[derive(Deserialize)]
enum Ignore {
    None,
    All,
    Some(Vec<String>),
}

#[derive(Deserialize)]
struct Code {
    crate_level: String,
    code: String,
    wrapper: Option<Wrapper>,
}

const PRELUDE: &str = "#![allow(unused)]\n";

impl Code {
    /// Recover rustdoc's merged declarations and untrimmed body from the standalone extraction.
    /// Leave interleaved extern crates to rustdoc when we cannot locate the body in the input.
    fn merged_parts<'a>(&'a self, original: &'a str, injected: &str) -> Option<(&'a str, &'a str)> {
        let declarations = self.crate_level.strip_prefix(PRELUDE)?;
        let declarations = if original.starts_with(declarations.trim_end()) {
            declarations
        } else {
            declarations.strip_suffix(injected)?
        }
        .trim_end();
        let input = original.strip_prefix(declarations)?;
        if self.code.is_empty() {
            return Some((declarations, ""));
        }
        let trailing = input.trim_start().strip_prefix(self.code.as_str())?;
        Some((declarations, &input[..input.len() - trailing.len()]))
    }
}

#[derive(Deserialize)]
struct Wrapper {
    returns_result: bool,
}

/// Sources for the example library and its libtest executable.
#[derive(Default)]
pub(super) struct Harness {
    pub(super) examples: String,
    pub(super) driver: String,
}

/// Generates one executable for mergeable examples. Rustdoc owns the crate if
/// any example requires its standalone compiler or a different language mode.
pub(super) fn harness(json: &[u8], crate_name: &str) -> Option<Harness> {
    let mut extraction: Extraction = serde_json::from_slice(json).ok()?;
    if extraction.format_version != 2 {
        return None;
    }
    extraction.doctests.sort_by(|a, b| {
        a.standalone()
            .cmp(&b.standalone())
            .then_with(|| a.name.cmp(&b.name))
    });
    // Keep the bundle layout identical to librustdoc::doctest::runner so locations
    // observed by macros in dependencies and #[track_caller] stay accurate.
    let mut source = format!("\n{PRELUDE}");
    let injected = format!("#[allow(unused_extern_crates)]\nextern crate r#{crate_name};\n");
    let mut arms = String::new();
    let mut driver = String::from(include_str!("harness.rs"));
    driver.push_str("\nconst CASES: &[Case] = &[\n");
    for (id, example) in extraction.doctests.into_iter().enumerate() {
        let standalone = example.standalone();
        let attrs = example.doctest_attributes;
        let ignore = match attrs.ignore {
            Ignore::None => false,
            Ignore::All => true,
            Ignore::Some(_targets) => return None,
        };
        writeln!(driver, "Case {{ name: {:?}, file: {:?}, line: {}, ignore: {ignore}, no_run: {}, should_panic: {} }},",
            example.name, example.file, example.line, attrs.no_run, attrs.should_panic).unwrap();
        if ignore && standalone {
            continue;
        }
        if standalone
            || attrs.edition.is_some()
            || !attrs.error_codes.is_empty()
            || !attrs.unknown.is_empty()
            || (attrs.should_panic && attrs.no_run)
            || needs_crate_root(
                example.original_code.parse().ok()?,
                example.original_code.contains("$crate"),
            )
        {
            return None;
        }
        let code = example.doctest_code?;
        let (declarations, body) = code.merged_parts(&example.original_code, &injected)?;
        if ignore {
            writeln!(source, "pub mod __doctest_{id} {{}}\n").unwrap();
            continue;
        }
        writeln!(source, "pub mod __doctest_{id} {{\n{declarations}").unwrap();
        if let Some(wrapper) = &code.wrapper {
            let returns_result = if wrapper.returns_result {
                "-> Result<(), impl core::fmt::Debug>"
            } else {
                ""
            };
            writeln!(source, "fn main() {returns_result} {{\n{body}\n}}").unwrap();
        } else {
            writeln!(source, "{body}").unwrap();
        }
        source.push_str("pub fn __main_fn() -> impl std::process::Termination { main() } \n}\n\n");
        writeln!(
            arms,
            "{id} => test::assert_test_result(__ohm_doctest_examples::__doctest_{id}::__main_fn()).report(),"
        )
        .unwrap();
    }
    if arms.is_empty() {
        return None;
    }
    driver.push_str("];\n");
    writeln!(
        driver,
        "fn run_example(id: usize) -> ExitCode {{ match id {{\n{arms}_ => unreachable!(),\n}} }}"
    )
    .unwrap();
    Some(Harness {
        examples: source,
        driver,
    })
}

/// Location macros and crate-root items can change meaning when moved into a
/// module. Inspect tokens so words in a string or comment don't disable a crate.
fn needs_crate_root(tokens: TokenStream, mentions_dollar_crate: bool) -> bool {
    let mut tokens = tokens.into_iter().peekable();
    while let Some(token) = tokens.next() {
        match token {
            TokenTree::Group(group) if needs_crate_root(group.stream(), mentions_dollar_crate) => {
                return true;
            }
            TokenTree::Ident(ident) => {
                let next = match tokens.peek() {
                    Some(TokenTree::Punct(punct)) => Some(punct.as_char()),
                    _ => None,
                };
                match ident.to_string().trim_start_matches("r#") {
                    // rustdoc keeps macro definitions with a textual `$crate` in a standalone crate.
                    "macro_rules" | "macro" if mentions_dollar_crate => return true,
                    "crate" | "super" if next == Some(':') => return true,
                    "file" | "line" | "column" | "module_path" | "include" | "include_str"
                    | "include_bytes"
                        if next == Some('!') =>
                    {
                        return true;
                    }
                    "test" | "macro_export" | "global_allocator" | "no_mangle" | "export_name" => {
                        return true;
                    }
                    _ => {}
                }
            }
            // A crate-level inner attribute in the original example may not be
            // valid (or have the same effect) inside a generated module.
            TokenTree::Punct(p)
                if p.as_char() == '#'
                    && matches!(tokens.peek(), Some(TokenTree::Punct(p)) if p.as_char() == '!') =>
            {
                return true;
            }
            _ => {}
        }
    }
    false
}
