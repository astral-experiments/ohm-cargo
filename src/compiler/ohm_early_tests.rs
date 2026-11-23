use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Condvar, Mutex};

use cargo_util::paths;

use super::{BuildRunner, CompileMode, FileFlavor, Unit, unused_integration_self_dependency};
use crate::util::data_structures::HashSet;
use crate::util::interning::InternedString;
use crate::util::{self, CargoResult};

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

    /// The scheduler has accepted or rejected the producer and all of its dependencies.
    pub(crate) fn is_finished(&self) -> bool {
        self.result.lock().unwrap().is_some()
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

/// A check can veto speculation, but can never authorize native output reuse.
/// A successful native compilation supersedes this hint; stale hints can only
/// defer one compilation until its library finishes.
pub(crate) struct CheckHint {
    path: PathBuf,
    library: InternedString,
}

impl CheckHint {
    pub(crate) fn new(runner: &BuildRunner<'_, '_>, unit: &Unit, library: InternedString) -> Self {
        let key = util::short_hash(&(
            unit.pkg.package_id().stable_hash(runner.bcx.ws.root()),
            &unit.target,
            unit.kind.fingerprint_hash(),
            &unit.features,
            &unit.profile,
            &unit.rustflags,
            runner.bcx.extra_args_for(unit),
            &runner.bcx.rustc().verbose_version,
            library,
        ));
        Self {
            path: runner
                .files()
                .incremental_dir(unit)
                .join("ohm-early-test-check-v1")
                .join(key),
            library,
        }
    }

    fn vetoes_speculation(&self) -> bool {
        const HINT: &[u8] = b"uses-library\n";
        paths::read_regular_bounded(&self.path, HINT.len() as u64).is_ok_and(|bytes| bytes == HINT)
    }

    /// A failed or uninformative new check must not leave an older hint behind.
    pub(crate) fn clear(&self) {
        if let Err(error) = fs::remove_file(&self.path)
            && error.kind() != std::io::ErrorKind::NotFound
        {
            tracing::debug!(?error, "could not clear early-test check hint");
        }
    }

    pub(crate) fn record(&self, unused: Option<&BTreeSet<InternedString>>) {
        if !unused.is_some_and(|unused| !unused.contains(&self.library)) {
            return;
        }
        let result = paths::create_dir_all(self.path.parent().unwrap())
            .and_then(|()| paths::write_atomic_no_follow(&self.path, b"uses-library\n"));
        if let Err(error) = result {
            tracing::debug!(?error, "could not record early-test check hint");
        }
    }
}

/// Preserve dependency-only skip/relink paths while overlapping compilations
/// that need rustc anyway. Warm builds require prior unused-library evidence
/// tied to their executable; current compiler proof still decides acceptance.
pub(crate) fn dependency(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    previous_unused_externs: Option<&HashSet<InternedString>>,
    check_hint: Option<&CheckHint>,
) -> Option<(Unit, InternedString)> {
    if !runner.bcx.gctx.cli_unstable().ohm_early_tests()
        || runner.bcx.build_config.jobs < 2
        || !runner.headstart_enabled()
        || unit.mode != CompileMode::Test
        || !unit.target.is_test()
        || check_hint.is_some_and(CheckHint::vetoes_speculation)
    {
        return None;
    }
    let (index, name) = unused_integration_self_dependency(runner, unit)?;
    let has_executable = runner
        .outputs(unit)
        .ok()?
        .iter()
        .any(|output| output.flavor == FileFlavor::Normal && output.path.exists());
    if has_executable
        && (previous_unused_externs.is_none_or(|unused| !unused.contains(&name))
            || runner.fingerprints.get(unit).is_none_or(|fingerprint| {
                fingerprint.is_early_cutoff_candidate()
                    || !matches!(
                        fingerprint.fs_status(),
                        super::fingerprint::FsStatus::StaleItem(_)
                    )
            }))
    {
        return None;
    }
    let dependency = runner
        .unit_deps(unit)
        .iter()
        .find(|dependency| runner.bcx.unit_to_index[&dependency.unit] == index)?;
    Some((dependency.unit.clone(), name))
}

/// Locates the producer's output rules when a wrapper can add arguments Cargo cannot see.
pub(super) fn wrapped_library_dep_info(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
) -> Option<PathBuf> {
    let rustc = runner.bcx.rustc();
    (rustc.wrapper.is_some()
        || (rustc.workspace_wrapper.is_some() && runner.bcx.ws.is_member_id(unit.pkg.package_id())))
    .then(|| {
        runner
            .files()
            .output_dir(unit)
            .join(super::rustc_dep_info_name(runner, unit))
    })
}

/// Accept only the three ordinary output rules of an rlib compilation.
/// A wrapper can request additional files anywhere, including in the source tree.
pub(super) fn has_only_library_outputs(dep_info: &Path) -> bool {
    let Ok(bytes) = paths::read_regular_bounded(dep_info, 4 * 1024 * 1024) else {
        return false;
    };
    let Ok(contents) = std::str::from_utf8(&bytes) else {
        return false;
    };
    let Some(stem) = dep_info.file_stem().and_then(|s| s.to_str()) else {
        return false;
    };
    let rlib = dep_info.with_file_name(format!("lib{stem}.rlib"));
    let rmeta = dep_info.with_file_name(format!("lib{stem}.rmeta"));
    let mut expected = BTreeSet::from([dep_info, rlib.as_path(), rmeta.as_path()]);
    // Only nonempty rustc rules have the ": " separator. Unfamiliar target
    // spellings (including escaped paths) take the ordinary build path.
    for (target, _) in contents.lines().filter_map(|line| line.split_once(": ")) {
        if !expected.remove(Path::new(target)) {
            return false;
        }
    }
    expected.is_empty()
}

/// An unused `--extern` does not rule out an `include_bytes!` of the library.
/// A producer can also replace dep-info and extra compiler outputs such as MIR.
/// Reject inputs in the build directory, including aliases through symlinked directories.
pub(super) fn has_independent_inputs(
    dep_info: &Path,
    cwd: &Path,
    build_dir: &Path,
    test_cwd: Option<&Path>,
) -> bool {
    let Ok(info) = super::fingerprint::parse_rustc_dep_info(dep_info) else {
        return false;
    };
    let Ok(build_dir) = build_dir.canonicalize() else {
        return false;
    };
    let is_artifact = |path: &Path| {
        path.starts_with(&build_dir)
            || path.extension().is_some_and(|ext| {
                ext.eq_ignore_ascii_case("rlib") || ext.eq_ignore_ascii_case("rmeta")
            })
    };
    // An early integration test waits for its library before running, but a
    // deferred dependency can still be stale when a test passes an env! path
    // to a subprocess. Resolve those paths from the package where tests run.
    let runtime_inputs = info.env.iter().filter_map(|(_, value)| {
        let path = test_cwd?.join(value.as_deref()?);
        (is_artifact(&path) || path.is_file()).then_some(path)
    });
    let files = info.files.keys().map(|file| cwd.join(file));
    !info.files.is_empty()
        && files.chain(runtime_inputs).all(|path| {
            // A hard link can name a compiler output even after canonicalization.
            #[cfg(unix)]
            if !path
                .metadata()
                .is_ok_and(|metadata| std::os::unix::fs::MetadataExt::nlink(&metadata) == 1)
            {
                return false;
            }
            !is_artifact(&path) && path.canonicalize().is_ok_and(|p| !is_artifact(&p))
        })
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
        !self.overflowed && proves_unused(self.stderr.iter().map(String::as_str), name)
    }
}

/// Read the same notification from the cached diagnostics as a profitability hint.
pub(super) fn previously_unused(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    name: InternedString,
) -> bool {
    let cache = runner.files().message_cache_path(unit);
    let Ok(messages) = paths::read_regular_bounded(&cache, 1024 * 1024) else {
        return false;
    };
    std::str::from_utf8(&messages).is_ok_and(|lines| proves_unused(lines.lines(), name))
}

/// Require a consistent compiler notification. Missing,
/// malformed, or conflicting records always take the ordinary compilation path.
fn proves_unused<'a>(lines: impl IntoIterator<Item = &'a str>, name: InternedString) -> bool {
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
        assert!(!completion.is_finished());
        drop(completion.guard());
        assert!(completion.is_finished());
        assert!(completion.wait().is_err());
        let completion = Arc::new(Completion::default());
        completion.guard().finish(true);
        assert!(completion.is_finished());
        assert!(completion.wait().is_ok());
    }
}
