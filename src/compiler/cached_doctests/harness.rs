// The examples are compiled in a separate crate with their own feature gates.
#![feature(test)]
extern crate test;
#[cfg(not(ohm_borrowed_libtest))]
use std::boxed::Box as TestCallback;
use std::process::{Command, ExitCode, Termination};
#[cfg(ohm_borrowed_libtest)]
use std::sync::Arc as TestCallback;

struct Case {
    name: &'static str,
    file: &'static str,
    line: usize,
    ignore: bool,
    no_run: bool,
    should_panic: bool,
}

fn main() -> ExitCode {
    let args: Vec<_> = std::env::args().collect();
    const RUN_OPTION: &str = "RUSTDOC_DOCTEST_RUN_NB_TEST";
    if let Ok(id) = std::env::var(RUN_OPTION) {
        return run_example(id.parse().expect("doctest index"));
    }

    // Cargo launches this driver directly at an absolute path. Use that same
    // path for children, including when a symlink hides a non-UTF-8 component.
    let exe = &args[0];
    let tests: Vec<_> = CASES
        .iter()
        .enumerate()
        .map(|(id, case)| {
            let exe = exe.clone();
            test::TestDescAndFn {
                desc: test::TestDesc {
                    name: test::StaticTestName(case.name),
                    ignore: case.ignore,
                    ignore_message: None,
                    source_file: case.file,
                    start_line: case.line,
                    end_line: case.line,
                    start_col: 0,
                    end_col: 0,
                    should_panic: if case.should_panic {
                        test::ShouldPanic::Yes
                    } else {
                        test::ShouldPanic::No
                    },
                    compile_fail: false,
                    no_run: case.no_run,
                    test_type: test::TestType::DocTest,
                },
                testfn: test::DynTestFn(TestCallback::new(move || {
                    if case.no_run {
                        return Ok(());
                    }
                    // An example may exit, change cwd, or modify the process environment.
                    let output = Command::new(&exe)
                        .env(RUN_OPTION, id.to_string())
                        .output()
                        .unwrap_or_else(|error| {
                            eprintln!("could not launch doctest: {error}");
                            std::process::exit(1)
                        });
                    if output.status.success() {
                        return Ok(());
                    }
                    match output.status.code() {
                        Some(code) => eprintln!("Test executable failed (exit status: {code})."),
                        None => eprintln!("Test executable failed (terminated by signal)."),
                    }
                    if !output.stdout.is_empty() || !output.stderr.is_empty() {
                        eprintln!();
                    }
                    for (label, bytes) in [("stdout", output.stdout), ("stderr", output.stderr)] {
                        if !bytes.is_empty() {
                            eprintln!("{label}:\n{}", String::from_utf8_lossy(&bytes));
                        }
                    }
                    test::assert_test_result(ExitCode::FAILURE)
                })),
            }
        })
        .collect();
    #[cfg(ohm_borrowed_libtest)]
    {
        test::test_main(&args, &tests.iter().collect::<Vec<_>>())
    }
    #[cfg(not(ohm_borrowed_libtest))]
    {
        test::test_main(&args, tests, None);
        ExitCode::SUCCESS
    }
}
