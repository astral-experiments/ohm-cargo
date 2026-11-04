// The examples are compiled in a separate crate with their own feature gates.
#![feature(test)]
extern crate test;
use std::process::{Command, ExitCode};

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
        return __ohm_doctest_examples::run_example(id.parse().expect("doctest index"));
    }

    let exe = std::env::current_exe().expect("doctest executable path");
    let tests = CASES
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
                testfn: test::DynTestFn(Box::new(move || {
                    if case.no_run {
                        return Ok(());
                    }
                    // An example may exit, change cwd, or modify the process environment.
                    let output = Command::new(exe)
                        .env(RUN_OPTION, id.to_string())
                        .output()
                        .unwrap_or_else(|error| {
                            eprintln!("could not launch doctest: {error}");
                            std::process::exit(1)
                        });
                    print!("{}", String::from_utf8_lossy(&output.stdout));
                    eprint!("{}", String::from_utf8_lossy(&output.stderr));
                    if output.status.success() {
                        Ok(())
                    } else {
                        Err(output.status.to_string())
                    }
                })),
            }
        })
        .collect();
    test::test_main(&args, tests, None);
    ExitCode::SUCCESS
}
