//! Cached executable jobs retain artifacts and diagnostics while dirty jobs
//! still wait for the complete native dependency closure.

use crate::prelude::*;
use cargo_test_support::{Project, project, str};

fn native_chain() -> Project {
    project()
        .file(
            "Cargo.toml",
            "[package]\nname='app'\nversion='0.1.0'\nedition='2024'\n[dependencies]\nmiddle={path='middle'}\n",
        )
        .file(
            "src/main.rs",
            "fn main() { println!(\"{}\", middle::value()); } fn replay_this_warning() {}",
        )
        .file("tests/integration.rs", "#[test] fn example() {}")
        .file(
            "middle/Cargo.toml",
            "[package]\nname='middle'\nversion='0.1.0'\nedition='2024'\n[dependencies]\nleaf={path='../leaf'}\n",
        )
        .file("middle/src/lib.rs", "pub fn value() -> u32 { leaf::value() }")
        .file(
            "leaf/Cargo.toml",
            "[package]\nname='leaf'\nversion='0.1.0'\nedition='2024'\n",
        )
        .file("leaf/src/lib.rs", "pub fn value() -> u32 { 1 }")
        .build()
}

#[cargo_test]
fn fresh_executables_replay_artifacts_and_diagnostics() {
    let p = native_chain();
    for command in ["check", "test --no-run"] {
        let invoke = || {
            let output = p
                .cargo(&format!(
                    "-Zohm-defaults=no {command} --message-format=json"
                ))
                .masquerade_as_nightly_cargo(&["ohm-defaults"])
                .exec_with_output()
                .unwrap();
            String::from_utf8(output.stdout)
                .unwrap()
                .lines()
                .map(|line| serde_json::from_str::<serde_json::Value>(line).unwrap())
                .collect::<Vec<_>>()
        };
        let first = invoke();
        let executable = (command == "test --no-run").then(|| p.bin("app"));
        if let Some(path) = &executable {
            std::fs::remove_file(path).unwrap();
        }
        let fresh = invoke();
        if let Some(path) = &executable {
            assert!(
                path.exists(),
                "fresh jobs must restore the root artifact link"
            );
        }
        let normalized = |messages: &[serde_json::Value], require_fresh: bool| {
            let mut result = Vec::new();
            let mut artifacts = 0;
            let mut warning = false;
            for message in messages {
                let mut message = message.clone();
                match message["reason"].as_str() {
                    Some("compiler-artifact") => {
                        artifacts += 1;
                        if require_fresh {
                            assert_eq!(message["fresh"], true);
                        }
                        message.as_object_mut().unwrap().remove("fresh");
                    }
                    Some("compiler-message") => {
                        warning |= message.to_string().contains("replay_this_warning");
                    }
                    _ => continue,
                }
                result.push(message.to_string());
            }
            assert!(artifacts >= 3);
            assert!(warning, "fresh jobs must replay cached warnings");
            result.sort();
            result
        };
        assert_eq!(normalized(&first, false), normalized(&fresh, true));
    }
}

#[cargo_test]
fn dirty_executables_link_transitive_changes_and_propagate_failures() {
    let p = native_chain();
    let build = || {
        p.cargo("-Zohm-defaults=no test --no-run -j 4")
            .masquerade_as_nightly_cargo(&["ohm-defaults"])
            .run();
    };
    build();
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
1

"#]])
        .run();
    p.change_file("leaf/src/lib.rs", "pub fn value() -> u32 { 2 }");
    build();
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
2

"#]])
        .run();

    p.change_file("leaf/src/lib.rs", "compile_error!(\"leaf failure\");");
    p.cargo("-Zohm-defaults=no test --no-run -j 4")
        .masquerade_as_nightly_cargo(&["ohm-defaults"])
        .with_status(101)
        .with_stderr_contains("[..]leaf failure[..]")
        .run();
    p.change_file("leaf/src/lib.rs", "pub fn value() -> u32 { 3 }");
    build();
    p.process(&p.bin("app"))
        .with_stdout_data(str![[r#"
3

"#]])
        .run();
}
