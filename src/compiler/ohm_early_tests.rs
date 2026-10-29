use std::sync::{Arc, Condvar, Mutex};

use super::{BuildRunner, CompileMode, FileFlavor, Unit, unused_integration_self_dependency};
use crate::util::CargoResult;
use crate::util::interning::InternedString;

/// A producer's final scheduler result, including denied warnings and dependencies.
#[derive(Default)]
pub(crate) struct Completion {
    result: Mutex<Option<bool>>,
    ready: Condvar,
}

impl Completion {
    fn finish(&self, succeeded: bool) {
        self.result.lock().unwrap().get_or_insert(succeeded);
        self.ready.notify_all();
    }

    pub(crate) fn guard(self: &Arc<Self>) -> CompletionGuard {
        CompletionGuard(Arc::clone(self))
    }

    pub(crate) fn wait(&self) -> CargoResult<()> {
        let result = self
            .ready
            .wait_while(self.result.lock().unwrap(), |result| result.is_none())
            .unwrap();
        anyhow::ensure!(*result == Some(true), "early test dependency failed");
        Ok(())
    }
}

/// Dropping a scheduler entry without accepting it must wake its waiting tests.
pub(crate) struct CompletionGuard(Arc<Completion>);

impl CompletionGuard {
    pub(crate) fn finish(self, succeeded: bool) {
        self.0.finish(succeeded);
    }
}

impl Drop for CompletionGuard {
    fn drop(&mut self) {
        self.0.finish(false);
    }
}

/// Restrict speculation to first native integration-test builds. The normal
/// command, all other dependencies, and final producer-success barrier remain.
pub(crate) fn dependency(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
) -> Option<(Unit, InternedString)> {
    if !runner.bcx.gctx.cli_unstable().ohm_early_tests()
        || runner.bcx.build_config.jobs < 2
        || !runner.headstart_enabled()
        || unit.mode != CompileMode::Test
        || !unit.target.is_test()
    {
        return None;
    }
    if runner
        .outputs(unit)
        .ok()?
        .iter()
        .any(|output| output.flavor == FileFlavor::Normal && output.path.exists())
    {
        return None;
    }
    let (index, name) = unused_integration_self_dependency(runner, unit)?;
    let dependency = runner
        .unit_deps(unit)
        .iter()
        .find(|dependency| runner.bcx.unit_to_index[&dependency.unit] == index)?;
    Some((dependency.unit.clone(), name))
}

/// Keep speculative diagnostics bounded. On overflow, discard them and retry
/// normally so the ordinary streaming path reports the complete diagnostics.
#[derive(Default)]
pub(crate) struct Output {
    pub(crate) stdout: Vec<String>,
    pub(crate) stderr: Vec<String>,
    bytes: usize,
    overflowed: bool,
}

impl Output {
    pub(crate) fn push(&mut self, line: &str, stderr: bool) {
        const LIMIT: usize = 1024 * 1024;
        if self.overflowed {
            return;
        }
        self.bytes = self.bytes.saturating_add(line.len() + size_of::<String>());
        if self.bytes > LIMIT {
            self.overflowed = true;
            self.stdout.clear();
            self.stderr.clear();
            return;
        }
        let stream = if stderr {
            &mut self.stderr
        } else {
            &mut self.stdout
        };
        stream.push(line.to_owned());
    }

    pub(crate) fn proves_unused(&self, name: InternedString) -> bool {
        !self.overflowed && proves_unused(&self.stderr, name)
    }
}

/// Require a consistent compiler notification from this invocation. Missing,
/// malformed, or conflicting records always take the ordinary compilation path.
fn proves_unused(lines: &[String], name: InternedString) -> bool {
    #[derive(serde::Deserialize, PartialEq)]
    struct UnusedExterns {
        unused_extern_names: std::collections::BTreeSet<InternedString>,
    }
    let mut recorded = None;
    for line in lines {
        let Ok(value) = serde_json::from_str::<serde_json::Value>(line) else {
            if line.contains("unused_extern") {
                return false;
            }
            continue;
        };
        if value.get("$message_type").and_then(|value| value.as_str()) != Some("unused_extern") {
            continue;
        }
        let Ok(unused) = serde_json::from_value::<UnusedExterns>(value) else {
            return false;
        };
        if recorded
            .as_ref()
            .is_some_and(|previous| previous != &unused)
        {
            return false;
        }
        recorded = Some(unused);
    }
    recorded.is_some_and(|record| record.unused_extern_names.contains(&name))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn provisional_output_requires_consistent_bounded_proof() {
        let proof = r#"{"$message_type":"unused_extern","unused_extern_names":["app"]}"#;
        let mut output = Output::default();
        assert!(!output.proves_unused("app".into()));
        output.push(proof, true);
        output.push(proof, true);
        assert!(output.proves_unused("app".into()));
        for invalid in [
            r#"{"$message_type":"unused_extern","unused_extern_names":[]}"#,
            r#"{"$message_type":"unused_extern","unused_extern_names":"app"}"#,
            r#"{"$message_type":"unused_extern""#,
        ] {
            let mut output = Output::default();
            output.push(proof, true);
            output.push(invalid, true);
            assert!(!output.proves_unused("app".into()));
        }
        output.push(&"x".repeat(1024 * 1024), false);
        output.push(proof, true);
        assert!(!output.proves_unused("app".into()));
        assert!(output.stderr.is_empty() && output.stdout.is_empty());
    }

    #[test]
    fn scheduler_drop_rejects_waiting_tests() {
        let completion = Arc::new(Completion::default());
        drop(completion.guard());
        assert!(completion.wait().is_err());
        let completion = Arc::new(Completion::default());
        completion.guard().finish(true);
        assert!(completion.wait().is_ok());
    }
}
