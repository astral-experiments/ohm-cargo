//! Immutable freshness results retained within one prepared check graph.
//!
//! Admission records values at the ordinary fingerprinting read sites. Taking a
//! second snapshot after deciding Fresh could instead retain a racing edit as
//! the input to a result that never consumed it.

use std::cell::RefCell;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use cargo_util::paths;
use filetime::FileTime;

use crate::core::compiler::unit_graph::UnitDep;
use crate::core::compiler::{BuildContext, Unit, UnitIndex};
use crate::util::data_structures::{HashMap, HashSet};

use super::{DepFingerprint, Fingerprint, FsStatus, LocalFingerprint};

#[derive(Default)]
pub(crate) struct SessionFreshness {
    state: RefCell<State>,
    eligible: HashSet<Unit>,
}

#[derive(Default)]
struct State {
    nodes: HashMap<Unit, Node>,
    version: u64,
}

struct Node {
    version: u64,
    dependencies: Vec<u64>,
    reads: ReadSet,
    template: Template,
}

/// Per-request bookkeeping; none of the current fingerprints enter the cache.
pub(crate) struct FreshnessRun<'a> {
    cache: &'a SessionFreshness,
    versions: HashMap<Unit, u64>,
    reads: HashMap<Unit, ReadSet>,
}

impl SessionFreshness {
    pub(crate) fn new(bcx: &BuildContext<'_, '_>) -> Self {
        fn eligible(
            bcx: &BuildContext<'_, '_>,
            unit: &Unit,
            memo: &mut HashMap<Unit, bool>,
        ) -> bool {
            if let Some(result) = memo.get(unit) {
                return *result;
            }
            // Mark first so an unexpected cycle conservatively rejects reuse.
            memo.insert(unit.clone(), false);
            let result = unit.mode.is_check()
                && unit.target.is_lib()
                && !unit.target.proc_macro()
                && !unit.artifact.is_true()
                && bcx.unit_graph[unit]
                    .iter()
                    .all(|dep| eligible(bcx, &dep.unit, memo));
            memo.insert(unit.clone(), result);
            result
        }
        let mut memo = HashMap::default();
        for unit in bcx.unit_graph.keys() {
            eligible(bcx, unit, &mut memo);
        }
        Self {
            state: RefCell::default(),
            eligible: memo
                .into_iter()
                .filter_map(|(unit, yes)| yes.then_some(unit))
                .collect(),
        }
    }

    pub(crate) fn start(&self) -> FreshnessRun<'_> {
        FreshnessRun {
            cache: self,
            versions: HashMap::default(),
            reads: HashMap::default(),
        }
    }
}

impl FreshnessRun<'_> {
    /// Validate children before their parent; a recomputation gets a new version
    /// even if its eventual fingerprint hash happens to stay the same.
    pub(super) fn reuse(
        &mut self,
        unit: &Unit,
        unit_deps: &[UnitDep],
        deps: Vec<DepFingerprint>,
        index: UnitIndex,
    ) -> Result<Fingerprint, Vec<DepFingerprint>> {
        if !self.cache.eligible.contains(unit) {
            return Err(deps);
        }
        let dependencies = self.dependency_versions(unit_deps);
        let mut state = self.cache.state.borrow_mut();
        if let Some(node) = state.nodes.get(unit) {
            if dependencies.as_ref() == Some(&node.dependencies) && node.reads.validate() {
                self.versions.insert(unit.clone(), node.version);
                tracing::trace!(package = %unit.pkg, "session freshness hit");
                return Ok(node.template.instantiate(deps, index));
            }
        }
        state.nodes.remove(unit);
        state.version += 1;
        self.versions.insert(unit.clone(), state.version);
        self.reads.insert(unit.clone(), ReadSet::default());
        Err(deps)
    }

    fn dependency_versions(&self, deps: &[UnitDep]) -> Option<Vec<u64>> {
        deps.iter()
            .map(|dep| self.versions.get(&dep.unit).copied())
            .collect()
    }

    pub(super) fn reads(&mut self, unit: &Unit) -> Option<&mut ReadSet> {
        self.reads.get_mut(unit)
    }

    /// Publish only an ordinary Fresh comparison, with its consumed read set.
    pub(super) fn publish(&mut self, unit: &Unit, deps: &[UnitDep], fingerprint: &Fingerprint) {
        let Some(reads) = self.reads.remove(unit) else {
            return;
        };
        if reads.invalid {
            return;
        }
        let Some(dependencies) = self.dependency_versions(deps) else {
            return;
        };
        let Some(template) = Template::capture(fingerprint) else {
            return;
        };
        self.cache.state.borrow_mut().nodes.insert(
            unit.clone(),
            Node {
                version: self.versions[unit],
                dependencies,
                reads,
                template,
            },
        );
    }
}

/// Copy only immutable inputs and the proven UpToDate payload. All mutable
/// fingerprint state starts anew, and dependency Arcs belong to this request.
struct Template {
    rustc: u64,
    features: String,
    declared_features: String,
    target: u64,
    profile: u64,
    path: u64,
    dep_info: PathBuf,
    rustflags: Vec<String>,
    config: u64,
    compile_kind: u64,
    outputs: Vec<PathBuf>,
    mtimes: HashMap<PathBuf, FileTime>,
    link_mtime: Option<FileTime>,
}

impl Template {
    fn capture(fingerprint: &Fingerprint) -> Option<Self> {
        if fingerprint.ohm_worktree_namespace.is_some() {
            return None;
        }
        let local = fingerprint.local.lock().unwrap();
        let [
            LocalFingerprint::CheckDepInfo {
                dep_info,
                checksum: false,
            },
        ] = local.as_slice()
        else {
            return None;
        };
        let fs_status = fingerprint.fs_status.lock().unwrap();
        let FsStatus::UpToDate { mtimes, link_mtime } = &*fs_status else {
            return None;
        };
        Some(Self {
            rustc: fingerprint.rustc,
            features: fingerprint.features.clone(),
            declared_features: fingerprint.declared_features.clone(),
            target: fingerprint.target,
            profile: fingerprint.profile,
            path: fingerprint.path,
            dep_info: dep_info.clone(),
            rustflags: fingerprint.rustflags.clone(),
            config: fingerprint.config,
            compile_kind: fingerprint.compile_kind,
            outputs: fingerprint.outputs.clone(),
            mtimes: mtimes.clone(),
            link_mtime: *link_mtime,
        })
    }

    fn instantiate(&self, deps: Vec<DepFingerprint>, index: UnitIndex) -> Fingerprint {
        let mut fingerprint = Fingerprint::new();
        fingerprint.rustc = self.rustc;
        fingerprint.features = self.features.clone();
        fingerprint.declared_features = self.declared_features.clone();
        fingerprint.target = self.target;
        fingerprint.profile = self.profile;
        fingerprint.path = self.path;
        fingerprint.deps = deps;
        *fingerprint.local.get_mut().unwrap() = vec![LocalFingerprint::CheckDepInfo {
            dep_info: self.dep_info.clone(),
            checksum: false,
        }];
        fingerprint.rustflags = self.rustflags.clone();
        fingerprint.config = self.config;
        fingerprint.compile_kind = self.compile_kind;
        fingerprint.index = index;
        fingerprint.outputs = self.outputs.clone();
        *fingerprint.fs_status.get_mut().unwrap() = FsStatus::UpToDate {
            mtimes: self.mtimes.clone(),
            link_mtime: self.link_mtime,
        };
        fingerprint
    }
}

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum ReadKind {
    Bytes,
    Mtime,
    Canonical,
}

#[derive(PartialEq, Eq)]
enum Value {
    Bytes(Vec<u8>),
    Mtime(FileTime),
    Canonical(PathBuf),
}

/// Typed observations preserve logical path spelling and reject conflicting
/// repeated reads instead of silently replacing a value used by fingerprinting.
#[derive(Default)]
pub(super) struct ReadSet {
    values: BTreeMap<(PathBuf, ReadKind), Value>,
    invalid: bool,
}

impl ReadSet {
    fn insert(&mut self, path: &Path, kind: ReadKind, value: Value) {
        use std::collections::btree_map::Entry;
        match self.values.entry((path.to_path_buf(), kind)) {
            Entry::Vacant(entry) => {
                entry.insert(value);
            }
            Entry::Occupied(entry) => self.invalid |= *entry.get() != value,
        }
    }

    pub(super) fn bytes(&mut self, path: &Path, bytes: &[u8]) {
        self.insert(path, ReadKind::Bytes, Value::Bytes(bytes.to_vec()));
    }

    pub(super) fn mtime(&mut self, path: &Path, mtime: FileTime) {
        // mtime_recursive also accepts directories. Their complete traversal is
        // outside this cache's contract, so admit only regular file targets.
        if regular_file_mtime(path) != Some(mtime) {
            self.invalid = true;
            return;
        }
        self.insert(path, ReadKind::Mtime, Value::Mtime(mtime));
    }

    pub(super) fn canonical(&mut self, path: &Path, canonical: &Path) {
        self.insert(
            path,
            ReadKind::Canonical,
            Value::Canonical(canonical.to_path_buf()),
        );
    }

    fn validate(&self) -> bool {
        !self.invalid
            && self
                .values
                .iter()
                .all(|((path, _), expected)| match expected {
                    Value::Bytes(bytes) => {
                        paths::read_bytes(path).is_ok_and(|current| current == *bytes)
                    }
                    Value::Mtime(mtime) => regular_file_mtime(path) == Some(*mtime),
                    Value::Canonical(canonical) => crate::util::try_canonicalize(path)
                        .is_ok_and(|current| current == *canonical),
                })
    }
}

fn regular_file_mtime(path: &Path) -> Option<FileTime> {
    let metadata = fs::metadata(path).ok()?;
    metadata
        .is_file()
        .then(|| FileTime::from_last_modification_time(&metadata))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn consumed_values_cannot_be_replaced_by_a_later_snapshot() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("input.rs");
        fs::write(&path, "before").unwrap();
        let consumed = paths::read_bytes(&path).unwrap();
        let mtime = regular_file_mtime(&path).unwrap();
        fs::write(&path, "after").unwrap();
        filetime::set_file_mtime(
            &path,
            FileTime::from_unix_time(mtime.unix_seconds() + 10, 0),
        )
        .unwrap();

        let mut bytes = ReadSet::default();
        bytes.bytes(&path, &consumed);
        assert!(!bytes.validate());
        // A value served from this request's mtime cache must agree with the
        // regular-file observation before it can be admitted across requests.
        let mut mtimes = ReadSet::default();
        mtimes.mtime(&path, mtime);
        assert!(mtimes.invalid);
        assert!(!mtimes.validate());
    }

    #[test]
    fn repeated_reads_preserve_conflicts_and_operation_types() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("input.rs");
        fs::write(&path, "first").unwrap();
        let mut reads = ReadSet::default();
        reads.bytes(&path, b"first");
        reads.mtime(&path, regular_file_mtime(&path).unwrap());
        assert!(reads.validate());
        fs::write(&path, "second").unwrap();
        reads.bytes(&path, b"second");
        assert!(reads.invalid);
        assert!(!reads.validate());

        let mut directory_read = ReadSet::default();
        directory_read.mtime(directory.path(), paths::mtime(directory.path()).unwrap());
        assert!(directory_read.invalid);
    }
}
