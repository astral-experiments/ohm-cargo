#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
#[cargo_test]
fn dependency_edit_reassembles_native_targets_by_default() {
    let wrapper = relink_only_wrapper();
    let p = project()
        .file("Cargo.toml", &basic_manifest("app", "0.1.0"))
        .file("src/lib.rs", "pub fn value() -> u8 { 1 }")
        .file("payload.bin", "A")
        .file(
            "input.rs",
            r#"
                extern crate app;
                std::arch::global_asm!(concat!(
                    ".pushsection .rodata\n.globl payload\npayload:\n",
                    ".incbin \"", env!("CARGO_MANIFEST_DIR"), "/payload.bin\"\n.popsection"
                ));
                unsafe extern "C" { static payload: u8; }
                fn current() -> String { format!("{}:{}", app::value(), unsafe { payload }) }
            "#,
        )
        .file("src/bin/reader.rs", r#"include!("../../input.rs"); fn main() { println!("{}", current()); }"#)
        .file(
            "tests/integration.rs",
            r#"include!("../input.rs");
               #[test] fn reads_payload() { assert_eq!(current(), std::env::var("EXPECTED").unwrap()); }"#,
        )
        .build();
    let log = p.root().join("compiler.log");
    let test = |expected| {
        let mut cmd = p.cargo("-Zohm-defaults test --test integration");
        cmd.masquerade_as_nightly_cargo(&["ohm-defaults"])
            .env("CARGO_INCREMENTAL", "0")
            .env("RUSTC_WRAPPER", &wrapper)
            .env("RELINK_WRAPPER_LOG", &log)
            .env("EXPECTED", expected);
        cmd
    };
    test("1:65").run();
    fs::write(&log, "").unwrap();
    p.change_file("src/lib.rs", "pub fn value() -> u8 { 22 }");
    p.change_file("payload.bin", "B");
    test("22:66").run();
    p.process(&p.bin("reader"))
        .with_stdout_data("22:66\n")
        .run();

    // The wrapper also invokes rustc for an emulated link-only call. Check the
    // requested operation as well as the native value to distinguish the two.
    let calls = fs::read_to_string(&log).unwrap();
    let mut consumers: Vec<_> = calls
        .lines()
        .filter(|line| line.ends_with(":reader") || line.ends_with(":integration"))
        .collect();
    consumers.sort_unstable();
    assert_eq!(
        consumers,
        ["compile-link:integration", "compile-link:reader"],
        "{calls}"
    );

    p.change_file("src/lib.rs", "pub fn value() -> u8 { 3 }");
    fs::remove_file(p.root().join("payload.bin")).unwrap();
    test("")
        .with_status(101)
        .with_stderr_contains("[..]incbin file [..]payload.bin[..]")
        .run();
}
