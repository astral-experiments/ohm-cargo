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

#[derive(Deserialize)]
struct Wrapper {
    before: String,
    after: String,
}

/// Sources for the example library and its libtest executable.
#[derive(Default)]
pub(super) struct Harness {
    pub(super) examples: String,
    pub(super) driver: String,
}

/// Generates one executable for mergeable examples. Rustdoc owns the crate if
/// any example requires its standalone compiler or a different language mode.
pub(super) fn harness(json: &[u8]) -> Option<Harness> {
    let extraction: Extraction = serde_json::from_slice(json).ok()?;
    if extraction.format_version != 2 {
        return None;
    }
    let mut source = String::from("use ::std::process::Termination;\n");
    let mut arms = String::new();
    let mut driver = String::from(include_str!("harness.rs"));
    driver.push_str("\nconst CASES: &[Case] = &[\n");
    for (id, example) in extraction.doctests.into_iter().enumerate() {
        let attrs = example.doctest_attributes;
        let ignore = match attrs.ignore {
            Ignore::None => false,
            Ignore::All => true,
            Ignore::Some(_targets) => return None,
        };
        if !ignore {
            if attrs.compile_fail
                || attrs.standalone_crate
                || attrs.test_harness
                || attrs.edition.is_some()
                || !attrs.error_codes.is_empty()
                || !attrs.unknown.is_empty()
                || (attrs.should_panic && attrs.no_run)
                || needs_crate_root(example.original_code.parse().ok()?)
            {
                return None;
            }
            let code = example.doctest_code?;
            if code
                .crate_level
                .lines()
                .any(|line| line.starts_with("#![") && line != "#![allow(unused)]")
            {
                return None;
            }
            writeln!(source, "mod example_{id} {{\n{}", code.crate_level).unwrap();
            if let Some(wrapper) = code.wrapper {
                writeln!(source, "{}{}{}", wrapper.before, code.code, wrapper.after).unwrap();
            } else {
                writeln!(source, "{}", code.code).unwrap();
            }
            source.push_str(
                "pub(super) fn run() -> impl ::std::process::Termination { main() }\n}\n",
            );
            writeln!(arms, "{id} => example_{id}::run().report(),").unwrap();
        }
        writeln!(driver, "Case {{ name: {:?}, file: {:?}, line: {}, ignore: {ignore}, no_run: {}, should_panic: {} }},",
            example.name, example.file, example.line, attrs.no_run, attrs.should_panic).unwrap();
    }
    writeln!(source, "pub fn run_example(id: usize) -> ::std::process::ExitCode {{ match id {{\n{arms}_ => unreachable!(),\n}} }}").unwrap();
    driver.push_str("];\n");
    Some(Harness {
        examples: source,
        driver,
    })
}

/// Location macros and crate-root items can change meaning when moved into a
/// module. Inspect tokens so words in a string or comment don't disable a crate.
fn needs_crate_root(tokens: TokenStream) -> bool {
    let mut tokens = tokens.into_iter().peekable();
    while let Some(token) = tokens.next() {
        match token {
            TokenTree::Group(group) if needs_crate_root(group.stream()) => return true,
            TokenTree::Ident(ident) => {
                let next = match tokens.peek() {
                    Some(TokenTree::Punct(punct)) => Some(punct.as_char()),
                    _ => None,
                };
                match ident.to_string().trim_start_matches("r#") {
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
