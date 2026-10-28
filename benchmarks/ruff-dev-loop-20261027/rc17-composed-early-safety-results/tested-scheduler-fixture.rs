/// Exercise real compiler success/failure with deterministic scheduler overlap.
#[cargo_test]
#[cfg(not(windows))]
fn early_native_integration_tests_default_and_fallback() {
    let wrapper = relink_only_wrapper();
    for (case, flags, extra_env, used, fails, overlap, invocations) in [
        ("unused", "", None, false, false, true, 1),
        ("used", "", None, true, false, true, 2),
        ("built-library", "", None, true, false, false, 1),
        (
            "missing-proof",
            "",
            Some("EARLY_TEST_MISSING_PROOF"),
            false,
            false,
            true,
            2,
        ),
        (
            "conflicting-proof",
            "",
            Some("UNUSED_INTEGRATION_CONFLICTING_PROOF"),
            false,
            false,
            true,
            2,
        ),
        (
            "malformed-proof",
            "",
            Some("UNUSED_INTEGRATION_MALFORMED_PROOF"),
            false,
            false,
            true,
            2,
        ),
        ("producer-error", "", None, false, true, true, 1),
        ("denied-warning", "", None, false, true, true, 1),
        (
            "opt-out",
            "-Zohm-early-tests=no",
            None,
            false,
            false,
            false,
            1,
        ),
        ("serial", "", None, false, false, false, 1),
    ] {
        let p = project()
            .at(case)
            .file(
                "Cargo.toml",
                "[package]\nname=\"app\"\nversion=\"0.1.0\"\nedition=\"2024\"\n",
            )
            .file(
                "src/lib.rs",
                if case == "producer-error" {
                    "compile_error!(\"intentional producer failure\");"
                } else if case == "denied-warning" {
                    "pub fn value() -> u32 { 7 } fn unused() {}"
                } else {
                    "pub fn value() -> u32 { 7 }"
                },
            )
            .file(
                "tests/integration.rs",
                if used {
                    "#[test] fn works() { assert_eq!(app::value(), 7); }"
                } else {
                    "#[test] fn works() { assert_eq!(2 + 2, 4); }"
                },
            )
            .build();
        let log = p.root().join("wrapper.log");
        let jobs = if case == "serial" { 1 } else { 2 };
        if case == "built-library" {
            p.cargo("-Zohm-defaults -Zheadstart -Zsection-timings build --lib -j2")
                .masquerade_as_nightly_cargo(&["ohm-defaults", "headstart", "section-timings"])
                .env("RUSTC_WRAPPER", &wrapper)
                .env("RELINK_WRAPPER_LOG", &log)
                .env("EARLY_TEST_CONTROL", p.root())
                .run();
        }
        let mut command = p.cargo(&format!(
            "-Zohm-defaults -Zheadstart -Zsection-timings test --test integration -j{jobs} {flags}"
        ));
        if case == "denied-warning" {
            command.arg("--config").arg(r#"build.warnings="deny""#);
        }
        command
            .masquerade_as_nightly_cargo(&[
                "ohm-defaults",
                "headstart",
                "ohm-early-tests",
                "section-timings",
            ])
            .env("RUSTC_WRAPPER", &wrapper)
            .env("RELINK_WRAPPER_LOG", &log)
            .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1")
            .env("EARLY_TEST_CONTROL", p.root())
            .env("CARGO_LOG", "cargo::compiler::ohm_early_tests=info");
        if overlap {
            command.env("EARLY_TEST_EXPECT_OVERLAP", "1");
        }
        if let Some(key) = extra_env {
            command.env(key, "1");
        }
        if fails {
            command
                .with_status(101)
                .with_stdout_does_not_contain("[..]1 passed[..]")
                .with_stderr_does_not_contain("[..]accepted early integration[..]");
        } else {
            command.with_stdout_contains("[..]1 passed[..]");
            if overlap && invocations == 1 {
                command.with_stderr_contains("[..]accepted early integration[..]");
            } else if invocations == 2 {
                command
                    .with_stderr_contains("[..]retrying integration[..]")
                    .with_stderr_does_not_contain("[..]E0463[..]");
            }
        }
        command.run();
        if fails {
            assert!(
                fs::read_dir(p.target_debug_dir().join("deps"))
                    .unwrap()
                    .all(|entry| {
                        let name = entry.unwrap().file_name();
                        let name = name.to_string_lossy();
                        !(name.starts_with("integration-") && name.ends_with(".rlink-cache.json"))
                    })
            );
        }
        let calls = fs::read_to_string(&log).unwrap();
        assert_eq!(
            calls
                .lines()
                .filter(|line| line.ends_with(":integration"))
                .count(),
            invocations,
            "{case}: {calls}"
        );
        if case == "unused" {
            // An existing executable keeps ordinary freshness and native reuse.
            fs::write(&log, "").unwrap();
            p.cargo("-Zohm-defaults -Zheadstart -Zsection-timings test --test integration -j2")
                .masquerade_as_nightly_cargo(&["ohm-defaults", "headstart", "section-timings"])
                .env("RUSTC_WRAPPER", &wrapper)
                .env("RELINK_WRAPPER_LOG", &log)
                .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1")
                .run();
            assert!(fs::read_to_string(&log).unwrap().is_empty());
            // The earlier executable must not look older than its accepted
            // producer when a later, unused library change is considered.
            p.change_file("src/lib.rs", "pub fn value() -> u32 { 11 }");
            p.cargo("-Zohm-defaults -Zheadstart -Zsection-timings test --test integration -j2")
                .masquerade_as_nightly_cargo(&["ohm-defaults", "headstart", "section-timings"])
                .env("RUSTC_WRAPPER", &wrapper)
                .env("RELINK_WRAPPER_LOG", &log)
                .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1")
                .run();
            assert!(
                !fs::read_to_string(&log)
                    .unwrap()
                    .lines()
                    .any(|line| line.ends_with(":integration"))
            );
        }
    }
}

/// Prior proof controls warm admission; current proof controls acceptance.
#[cargo_test]
#[cfg(not(windows))]
fn early_native_integration_tests_warm_evidence_and_fallback() {
    let wrapper = relink_only_wrapper();
    for case in [
        "unused",
        "used",
        "missing-proof",
        "missing-manifest",
        "malformed-manifest",
        "old-version",
        "wrong-executable",
        "stale-executable",
        "opt-out",
        "new-use",
        "current-missing-proof",
        "producer-error",
        "checked-unused",
        "checked-new-use",
        "checked-missing-proof",
        "checked-other-features",
        "checked-then-unused",
    ] {
        let p = project()
            .at(case)
            .file(
                "Cargo.toml",
                "[package]\nname=\"app\"\nversion=\"0.1.0\"\nedition=\"2024\"\n[features]\nother = []\n",
            )
            .file("src/lib.rs", "pub fn value() -> u32 { 7 }")
            .file(
                "tests/integration.rs",
                if case == "used" {
                    "#[test] fn works() { assert_eq!(app::value(), 7); }"
                } else {
                    "#[test] fn works() { assert_eq!(2 + 2, 4); }"
                },
            )
            .build();
        let log = p.root().join("wrapper.log");
        let mut seed = p.cargo(
            "-Zohm-defaults -Zheadstart -Zsection-timings -Zohm-early-tests=no test --test integration -j2",
        );
        seed.masquerade_as_nightly_cargo(&[
            "ohm-defaults",
            "headstart",
            "section-timings",
            "ohm-early-tests",
        ])
        .env("RUSTC_WRAPPER", &wrapper)
        .env("RELINK_WRAPPER_LOG", &log)
        .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1");
        if case == "missing-proof" {
            seed.env("EARLY_TEST_MISSING_PROOF", "1");
        }
        seed.run();
        let manifest = fs::read_dir(p.target_debug_dir().join("deps"))
            .unwrap()
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .find(|path| {
                path.file_name()
                    .and_then(OsStr::to_str)
                    .is_some_and(|name| {
                        name.starts_with("integration-") && name.ends_with(".rlink-cache.json")
                    })
            })
            .expect("native integration-test manifest");
        let mut proof: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
        match case {
            "missing-manifest" => fs::remove_file(&manifest).unwrap(),
            "malformed-manifest" => fs::write(&manifest, b"{").unwrap(),
            "old-version" | "wrong-executable" | "stale-executable" => {
                match case {
                    "old-version" => proof["version"] = 0.into(),
                    "wrong-executable" => proof["executable"]["path"] = "wrong-executable".into(),
                    "stale-executable" => proof["executable"]["modified_nanos"] = 0.into(),
                    _ => unreachable!(),
                }
                fs::write(&manifest, serde_json::to_vec(&proof).unwrap()).unwrap();
            }
            _ => {}
        }
        fs::write(&log, "").unwrap();
        if is_coarse_mtime() {
            sleep_ms(1000);
        }
        p.change_file(
            "src/lib.rs",
            if case == "producer-error" {
                "compile_error!(\"intentional warm producer failure\");"
            } else {
                "pub fn value() -> u32 { 9 }"
            },
        );
        p.change_file(
            "tests/integration.rs",
            if matches!(
                case,
                "used"
                    | "new-use"
                    | "checked-new-use"
                    | "checked-missing-proof"
                    | "checked-other-features"
                    | "checked-then-unused"
            ) {
                "#[test] fn works() { assert_eq!(app::value(), 9); }"
            } else {
                "#[test] fn works() { assert_eq!(3 + 3, 6); }"
            },
        );
        if case.starts_with("checked-") {
            let mut check = p.cargo("-Zohm-defaults -Zheadstart check --test integration -j2");
            check
                .masquerade_as_nightly_cargo(&["ohm-defaults", "headstart"])
                .env("RUSTC_WRAPPER", &wrapper)
                .env("RELINK_WRAPPER_LOG", &log)
                .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1");
            if case == "checked-missing-proof" {
                check.env("EARLY_TEST_MISSING_PROOF", "1");
            }
            if case == "checked-other-features" {
                check.arg("--features=other");
            }
            check.run();
            fs::write(&log, "").unwrap();
            if case == "checked-then-unused" {
                p.change_file(
                    "tests/integration.rs",
                    "#[test] fn works() { assert_eq!(3 + 3, 6); }",
                );
            }
        }
        let overlap = matches!(
            case,
            "unused"
                | "new-use"
                | "current-missing-proof"
                | "producer-error"
                | "checked-unused"
                | "checked-missing-proof"
                | "checked-other-features"
        );
        let retry = matches!(
            case,
            "new-use"
                | "current-missing-proof"
                | "checked-missing-proof"
                | "checked-other-features"
        );
        let mut command =
            p.cargo("-Zohm-defaults -Zheadstart -Zsection-timings test --test integration -j2");
        command
            .masquerade_as_nightly_cargo(&[
                "ohm-defaults",
                "headstart",
                "section-timings",
                "ohm-early-tests",
            ])
            .env("RUSTC_WRAPPER", &wrapper)
            .env("RELINK_WRAPPER_LOG", &log)
            .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1")
            .env("EARLY_TEST_CONTROL", p.root())
            .env("CARGO_LOG", "cargo::compiler::ohm_early_tests=info");
        if overlap {
            command.env("EARLY_TEST_EXPECT_OVERLAP", "1");
        }
        if case == "opt-out" {
            command.arg("-Zohm-early-tests=no");
        }
        if case == "current-missing-proof" {
            command.env("EARLY_TEST_MISSING_PROOF", "1");
        }
        if case == "producer-error" {
            command
                .with_status(101)
                .with_stdout_does_not_contain("[..]1 passed[..]");
        } else {
            command.with_stdout_contains("[..]1 passed[..]");
        }
        if matches!(case, "unused" | "checked-unused") {
            command.with_stderr_contains("[..]accepted early integration[..]");
        } else {
            command.with_stderr_does_not_contain("[..]accepted early integration[..]");
        }
        if retry {
            command.with_stderr_contains("[..]retrying integration[..]");
        } else {
            command.with_stderr_does_not_contain("[..]retrying integration[..]");
        }
        command.run();
        let calls = fs::read_to_string(&log).unwrap();
        assert_eq!(
            calls
                .lines()
                .filter(|line| line.ends_with(":integration"))
                .count(),
            if retry { 2 } else { 1 },
            "{case}: {calls}"
        );
        if case == "producer-error" {
            assert!(!manifest.exists());
        } else if case == "new-use" {
            let proof: serde_json::Value =
                serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
            assert!(
                !proof["unused_extern_names"]
                    .as_array()
                    .unwrap()
                    .contains(&"app".into())
            );
        }
        if case == "checked-then-unused" {
            // A stale negative check hint only defers one native compilation.
            for marker in [
                "library-started",
                "library-finished",
                "test-started",
                "test-finished",
            ] {
                fs::remove_file(p.root().join(marker)).unwrap();
            }
            fs::write(&log, "").unwrap();
            if is_coarse_mtime() {
                sleep_ms(1000);
            }
            p.change_file("src/lib.rs", "pub fn value() -> u32 { 11 }");
            p.change_file(
                "tests/integration.rs",
                "#[test] fn works() { assert_eq!(4 + 4, 8); }",
            );
            p.cargo("-Zohm-defaults -Zheadstart -Zsection-timings test --test integration -j2")
                .masquerade_as_nightly_cargo(&["ohm-defaults", "headstart", "section-timings"])
                .env("RUSTC_WRAPPER", &wrapper)
                .env("RELINK_WRAPPER_LOG", &log)
                .env("UNUSED_INTEGRATION_DEPENDENCY_PROOF", "1")
                .env("EARLY_TEST_CONTROL", p.root())
                .env("EARLY_TEST_EXPECT_OVERLAP", "1")
                .env("CARGO_LOG", "cargo::compiler::ohm_early_tests=info")
                .with_stderr_contains("[..]accepted early integration[..]")
                .with_stdout_contains("[..]1 passed[..]")
                .run();
            assert_eq!(
                fs::read_to_string(&log)
                    .unwrap()
                    .matches(":integration\n")
                    .count(),
                1
            );
        }
    }
}
