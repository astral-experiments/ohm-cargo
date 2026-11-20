//! Unused libraries and build scripts with unchanged outputs can dirty an executable.
//! Pair the compiler's usage report with the native linker's dependency file.
use super::custom_build::BuildOutput;
use super::fingerprint::{self, Fingerprint};
use super::{
    BuildRunner, CompileKind, CompileMode, InternedString, RelinkCachePaths, Unit, UnitIndex,
};
use cargo_util::{ProcessBuilder, paths};
use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs::Metadata;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

pub(super) struct IndependentBinary {
    candidates: Vec<(UnitIndex, InternedString)>,
    script: Option<UnitIndex>,
    script_digest: Option<u64>,
    report: PathBuf,
    driver: PathBuf,
    dirs: BTreeSet<PathBuf>,
    native_roots: BTreeSet<PathBuf>,
    environment: Vec<Option<OsString>>,
    started: SystemTime,
}

impl IndependentBinary {
    /// Record the linker's own inputs for native workspace binaries built with
    /// the bundled ELF linker.
    pub(super) fn new(
        runner: &BuildRunner<'_, '_>,
        unit: &Unit,
        rustc: &mut ProcessBuilder,
        cache: &RelinkCachePaths,
    ) -> Option<Self> {
        if !cfg!(all(feature = "ohm-defaults", target_os = "linux"))
            || !((unit.target.is_bin() && unit.mode == CompileMode::Build)
                || (unit.target.is_test() && unit.mode == CompileMode::Test))
            || unit.kind != CompileKind::Host
            || !runner.bcx.ws.is_member_id(unit.pkg.package_id())
            || (unit.target.is_bin() && unit.pkg.has_custom_build())
            || runner.bcx.build_config.sbom
            || runner.bcx.build_config.future_incompat_report
            || runner.bcx.rustc().wrapper.is_some()
            || runner.bcx.rustc().workspace_wrapper.is_some()
            || runner.bcx.build_config.dry_run
            // The omitted suffix identifies flags Cargo added for the bundled linker.
            || runner.rustflags_for_cache_admission(unit).len() == unit.rustflags.len()
        {
            return None;
        }
        let mut script = None;
        let candidates = if unit.target.is_test() {
            // Packages with libraries already have scheduling and relink checks
            // for the implicit library edge.
            if unit.pkg.targets().iter().any(|target| target.is_lib())
                || super::cannot_use_extern_proof(runner, unit)
                || !macros_are_audited(runner)
            {
                return None;
            }
            let mut candidates = Vec::new();
            for dep in runner.unit_deps(unit) {
                let index = runner.bcx.unit_to_index[&dep.unit];
                if dep.unit.mode.is_run_custom_build() && dep.unit.pkg == unit.pkg {
                    script = Some(index);
                }
                if dep.unit.target.is_lib() && runner.bcx.ws.is_member_id(dep.unit.pkg.package_id())
                {
                    // All other externs count as used when checking transitive paths.
                    let names = [dep.extern_crate_name].into_iter().collect();
                    if super::unused_integration_workspace_dependencies(runner, unit, &names)
                        .contains(&index)
                    {
                        candidates.push((index, dep.extern_crate_name));
                    }
                }
            }
            if candidates.is_empty() {
                return None;
            }
            candidates
        } else {
            vec![super::implicit_library_dependency(runner, unit)?]
        };
        let driver = system_cc(rustc)?;
        let report = cache.objects.join("link.d");
        let arg = format!("-Clink-arg=--dependency-file={}", report.to_str()?);
        rustc.arg("-Clink-arg=-Xlinker").arg(arg);
        let environment = [
            "PATH",
            "LD_LIBRARY_PATH",
            "LD_RUN_PATH",
            "SOURCE_DATE_EPOCH",
        ]
        .into_iter()
        .map(|k| rustc.get_env(k))
        .collect();
        let dirs: BTreeSet<_> = ["/lib", "/usr/lib", "/lib64", "/usr/lib64"]
            .map(PathBuf::from)
            .into_iter()
            .collect();
        let native_roots = dirs
            .iter()
            .cloned()
            .chain([
                runner.bcx.gctx.registry_source_path().into_path_unlocked(),
                runner.bcx.target_data.info(unit.kind).sysroot.clone(),
            ])
            .filter_map(|dir| dir.canonicalize().ok())
            .collect();
        Some(Self {
            candidates,
            script,
            script_digest: None,
            report,
            driver,
            dirs,
            native_roots,
            environment,
            started: SystemTime::now(),
        })
    }

    /// A directory timestamp misses nested additions, symlink targets and
    /// in-place thin archive updates. Admit only native paths managed by
    /// the toolchain or immutable registry dependencies.
    pub(super) fn add_search_paths(
        &mut self,
        output: &BuildOutput,
        registry_out: &Path,
    ) -> Option<()> {
        if let Ok(dir) = registry_out.canonicalize() {
            self.native_roots.insert(dir);
        }
        for path in &output.library_paths {
            let path = path.as_ref().to_str()?;
            let path = path.split_once('=').map_or(path, |(_, path)| path);
            self.managed_native_input(Path::new(path))?;
            self.dirs.insert(path.into());
        }
        Some(())
    }

    fn managed_native_input(&self, path: &Path) -> Option<()> {
        let canonical = path.canonicalize().ok()?;
        self.native_roots
            .iter()
            .any(|root| canonical.starts_with(root))
            .then_some(())
    }

    pub(super) fn start(&mut self, fp: &Fingerprint) -> Option<()> {
        self.started = SystemTime::now();
        // Include the completed script's raw and parsed output and all generated
        // files in both snapshots, even across intervening builds of other roots.
        if let Some(index) = self.script {
            self.script_digest = Some(fp.script_digest(index)?);
        }
        Some(())
    }

    /// Ordinary compilation removes the entire object directory first.
    /// A link-only invocation needs the objects but can discard the report.
    pub(super) fn remove_report(&self) -> std::io::Result<()> {
        match std::fs::remove_file(&self.report) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
            result => result,
        }
    }

    pub(super) fn record(
        &self,
        cache: &RelinkCachePaths,
        names: &BTreeSet<InternedString>,
    ) -> Option<u64> {
        if !self.candidates.iter().any(|(_, name)| names.contains(name)) {
            return None;
        }
        self.snapshot(cache)
    }

    pub(super) fn reusable_inputs(
        &self,
        fp: &Fingerprint,
        cache: &RelinkCachePaths,
    ) -> Option<u64> {
        let (names, previous) = cache.unused_proof()?;
        let previous = previous?;
        let only_unused = self.candidates.iter().any(|(index, name)| {
            names.contains(name) && fingerprint::only_rebuilt_dependency(fp, *index)
        });
        let only_script = self
            .script
            .is_some_and(|index| fingerprint::only_rebuilt_dependency(fp, index));
        if !(only_unused || only_script) || self.snapshot(cache)? != previous {
            return None;
        }
        Some(previous)
    }

    fn snapshot(&self, cache: &RelinkCachePaths) -> Option<u64> {
        if !cache.has_object_directory() {
            return None;
        }
        let bytes = paths::read_regular_bounded(&self.report, 16 * 1024 * 1024).ok()?;
        let text = std::str::from_utf8(&bytes).ok()?;
        // Check both the output rule and the per-input rules. Do not
        // interpret ambiguous names or accept a truncated dependency file.
        let (rule, paths) = text.strip_suffix('\n')?.split_once("\n\n")?;
        let (out, mut remaining) = rule.split_once(':')?;
        if Path::new(out) != cache.executable {
            return None;
        }
        let mut hash = std::hash::DefaultHasher::new();
        ("binary-link-v2", &bytes, &self.environment).hash(&mut hash);
        if let Some(digest) = self.script_digest {
            digest.hash(&mut hash);
        }
        self.driver.hash(&mut hash);
        generation(&self.driver.metadata().ok()?, Some(self.started))?.hash(&mut hash);
        generation(&self.report.metadata().ok()?, None)?.hash(&mut hash);
        let mut dirs = self.dirs.clone();
        let mut symbols = false;
        let mut saw_objects = false;
        for path in paths.split("\n\n") {
            let path = path.strip_suffix(':')?;
            remaining = remaining.strip_prefix(' ')?.strip_prefix(path)?;
            if path.contains(['\\', '\n', '$', '#', ':']) {
                return None;
            }
            let path = Path::new(path);
            let parent = path.parent()?;
            // rustc removes its synthesized symbols object after linking.
            // Its generating inputs belong to the unchanged compiler unit.
            if path.file_name()? == "symbols.o"
                && parent.parent() == cache.executable.parent()
                && parent.file_name()?.to_str()?.starts_with("rustc")
                && !symbols
            {
                symbols = true;
                continue;
            }
            if parent == cache.objects {
                saw_objects = true;
            } else if path.extension().is_none_or(|s| s != "rlib") {
                self.managed_native_input(path)?;
            }
            if path.extension().is_none_or(|s| s != "o" && s != "rlib") {
                dirs.insert(parent.to_owned());
            }
            let metadata = path.metadata().ok()?;
            if !path.is_absolute() || !metadata.is_file() {
                return None;
            }
            let before = (parent != cache.objects).then_some(self.started);
            generation(&metadata, before)?.hash(&mut hash);
        }
        for dir in dirs {
            if !dir.is_absolute() {
                return None;
            }
            dir.hash(&mut hash);
            let metadata = match dir.metadata() {
                Ok(metadata) => metadata,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
                Err(_) => return None,
            };
            if !metadata.is_dir() {
                return None;
            }
            generation(&metadata, Some(self.started))?.hash(&mut hash);
        }
        (symbols && saw_objects && remaining.is_empty()).then(|| hash.finish())
    }
}

/// A procedural macro can read a file that only a script tracks. A matching
/// script result or unused-extern report cannot validate such a read. Check
/// the runtime closure against Cargo's configured registry macro policy.
fn macros_are_audited(runner: &BuildRunner<'_, '_>) -> bool {
    let mut pending: Vec<_> = runner
        .bcx
        .unit_graph
        .keys()
        .filter(|unit| unit.target.proc_macro())
        .collect();
    let mut visited = super::HashSet::default();
    while let Some(unit) = pending.pop() {
        if !visited.insert(unit) {
            continue;
        }
        if !runner
            .bcx
            .audited_proc_macro_packages
            .contains(&unit.pkg.package_id())
        {
            return false;
        }
        pending.extend(runner.unit_deps(unit).iter().map(|dep| &dep.unit));
    }
    true
}

/// A custom cc shim may handle even standard driver arguments differently.
/// Leave it alone unless it resolves directly to the system GCC or Clang.
fn system_cc(rustc: &ProcessBuilder) -> Option<PathBuf> {
    // Drivers can expand LIBRARY_PATH with multilib and multiarch directories.
    if ["GCC_EXEC_PREFIX", "COMPILER_PATH", "LIBRARY_PATH"]
        .iter()
        .any(|name| rustc.get_env(name).is_some())
    {
        return None;
    }
    for dir in std::env::split_paths(&rustc.get_env("PATH")?) {
        if !dir.is_absolute() {
            return None;
        }
        let path = dir.join("cc");
        if path.try_exists().ok()? {
            let driver = path.canonicalize().ok()?;
            return ["/usr/bin/gcc", "/usr/bin/clang"]
                .iter()
                .any(|p| Path::new(p).canonicalize().is_ok_and(|p| p == driver))
                .then_some(driver);
        }
    }
    None
}

/// External inputs must already have been stable when the binary job started.
/// Its own objects are written during the job and bound to the resulting proof.
fn generation(meta: &Metadata, before: Option<SystemTime>) -> Option<impl Hash> {
    #[cfg(all(
        feature = "ohm-defaults",
        target_os = "linux",
        target_arch = "x86_64",
        target_env = "gnu"
    ))]
    {
        use std::os::unix::fs::MetadataExt;
        if let Some(start) = before {
            let start = start.duration_since(SystemTime::UNIX_EPOCH).ok()?;
            if (meta.ctime(), meta.ctime_nsec())
                >= (
                    i64::try_from(start.as_secs()).ok()?,
                    i64::from(start.subsec_nanos()),
                )
            {
                return None;
            }
        }
        Some(super::native_link::stamp(meta))
    }
    #[cfg(not(all(
        feature = "ohm-defaults",
        target_os = "linux",
        target_arch = "x86_64",
        target_env = "gnu"
    )))]
    {
        let _ = (meta, before);
        None::<()>
    }
}
