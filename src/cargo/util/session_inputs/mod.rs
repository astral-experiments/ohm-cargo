//! Dependency recording for a session's coarse prepared-check computation.
//!
//! Observations are made at read sites, including negative observations. An
//! epoch never overwrites a conflicting read. Validation re-evaluates the same
//! typed queries and applies value equality before invalidating the consumer.

use std::collections::btree_map::Entry;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use anyhow::Context as _;

use crate::util::CargoResult;

#[cfg(target_os = "linux")]
mod cache;
#[cfg(target_os = "linux")]
mod watcher;

#[derive(Clone, Debug, Default)]
pub struct SessionInputs {
    graph: Arc<Mutex<Graph>>,
}

#[derive(Debug, Default)]
struct Graph {
    revision: u64,
    generation: u64,
    nodes: BTreeMap<InputKey, Node>,
    #[cfg(target_os = "linux")]
    cache: cache::InputCache,
}

#[derive(Debug)]
struct Node {
    value: InputValue,
    changed_at: u64,
    verified_at: u64,
}

impl Graph {
    /// Return the node version, advancing it only when an observed value changes.
    fn observe(&mut self, key: InputKey, value: InputValue) -> u64 {
        match self.nodes.entry(key) {
            Entry::Vacant(entry) => {
                entry.insert(Node {
                    value,
                    changed_at: self.revision,
                    verified_at: self.revision,
                });
                self.revision
            }
            Entry::Occupied(mut entry) => {
                let node = entry.get_mut();
                if node.value != value {
                    // Reads within one preparation must receive distinct versions
                    // when they disagree, even before the next validation starts.
                    self.revision += 1;
                    node.value = value;
                    node.changed_at = self.revision;
                }
                node.verified_at = self.revision;
                node.changed_at
            }
        }
    }
}

impl SessionInputs {
    /// Start a preparation before any configuration or workspace reads.
    pub fn begin(&self) -> InputTracker {
        // Only one epoch is live. Bound memory by releasing dependencies of the
        // retired epoch, while keeping the session's revision monotonic.
        let mut graph = self.graph.lock().unwrap();
        graph.revision += 1;
        graph.generation += 1;
        graph.nodes.clear();
        #[cfg(target_os = "linux")]
        {
            graph.cache = cache::InputCache::default();
        }
        let generation = graph.generation;
        drop(graph);
        InputTracker {
            graph: self.graph.clone(),
            reads: Arc::new(Mutex::new(ReadSet::default())),
            generation,
        }
    }
}

#[derive(Clone, Debug)]
pub struct InputTracker {
    graph: Arc<Mutex<Graph>>,
    reads: Arc<Mutex<ReadSet>>,
    generation: u64,
}

#[derive(Debug, Default)]
struct ReadSet {
    /// Versions of graph nodes consumed by this epoch.
    dependencies: BTreeMap<InputKey, u64>,
    conflict: Option<Invalidation>,
    fresh_only: BTreeSet<String>,
}

#[derive(Clone, Debug)]
pub struct Invalidation {
    reason: String,
}

impl std::fmt::Display for Invalidation {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.reason.fmt(f)
    }
}

impl std::error::Error for Invalidation {}

impl InputTracker {
    fn ensure_active(&self, graph: &Graph) -> Result<(), Invalidation> {
        if self.generation != graph.generation {
            return Err(Invalidation {
                reason: "session input epoch was retired".to_owned(),
            });
        }
        Ok(())
    }

    fn record(&self, key: InputKey, value: InputValue) {
        let mut reads = self.reads.lock().unwrap();
        let mut graph = self.graph.lock().unwrap();
        if let Err(retired) = self.ensure_active(&graph) {
            reads.conflict.get_or_insert(retired);
            return;
        }
        let observed = graph.observe(key.clone(), value);
        if let Some(expected) = reads.dependencies.get(&key) {
            if *expected != observed && reads.conflict.is_none() {
                reads.conflict = Some(Invalidation {
                    reason: format!("inconsistent reads of {key}"),
                });
            }
        } else {
            reads.dependencies.insert(key, observed);
        }
    }

    /// Validate all dependencies, including reads first reached during execution.
    pub fn validate(&self) -> Result<(), Invalidation> {
        let mut reads = self.reads.lock().unwrap();
        let mut graph = self.graph.lock().unwrap();
        if let Err(retired) = self.ensure_active(&graph) {
            reads.conflict.get_or_insert(retired);
        }
        if let Some(conflict) = &reads.conflict {
            return Err(conflict.clone());
        }
        graph.revision += 1;
        #[cfg(target_os = "linux")]
        let values = graph
            .cache
            .evaluate(&reads.dependencies.keys().collect::<Vec<_>>());
        #[cfg(not(target_os = "linux"))]
        let values = reads.dependencies.keys().map(InputKey::evaluate);
        let changed = reads
            .dependencies
            .iter()
            .zip(values)
            .find_map(|((key, expected), value)| {
                let observed = graph.observe(key.clone(), value);
                (observed != *expected).then(|| Invalidation {
                    reason: format!("{key} changed"),
                })
            });
        if let Some(changed) = changed {
            reads.conflict = Some(changed.clone());
            return Err(changed);
        }
        Ok(())
    }

    pub fn revision(&self) -> u64 {
        self.graph.lock().unwrap().revision
    }

    /// Disable reuse when a source or external query has undeclared inputs.
    pub fn require_fresh(&self, reason: impl Into<String>) {
        self.reads.lock().unwrap().fresh_only.insert(reason.into());
    }

    pub fn reuse_reason(&self) -> Option<String> {
        let reads = self.reads.lock().unwrap();
        (!reads.fresh_only.is_empty()).then(|| {
            reads
                .fresh_only
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>()
                .join("; ")
        })
    }

    /// Record bytes read through an existing Cargo file lock.
    pub fn observe_file(&self, path: &Path, bytes: &[u8]) {
        self.record(
            InputKey::File(path.to_owned()),
            InputValue::Bytes(Ok(bytes.into())),
        );
    }

    pub fn observe_file_error(&self, path: &Path, kind: io::ErrorKind) {
        self.record(
            InputKey::File(path.to_owned()),
            InputValue::Bytes(Err(kind)),
        );
    }

    pub fn observe_missing_file(&self, path: &Path) {
        self.record(
            InputKey::File(path.to_owned()),
            InputValue::Bytes(Err(io::ErrorKind::NotFound)),
        );
    }

    /// Publish exact bytes successfully authored by Cargo, preserving conflicts.
    ///
    /// This is reserved for input/output files such as Cargo.lock. Validation
    /// subsequently reads the path, so a competing writer cannot be adopted.
    pub fn publish_file(&self, path: &Path, bytes: &[u8]) {
        let mut reads = self.reads.lock().unwrap();
        let mut graph = self.graph.lock().unwrap();
        if let Err(retired) = self.ensure_active(&graph) {
            reads.conflict.get_or_insert(retired);
            return;
        }
        graph.revision += 1;
        let file = InputKey::File(path.to_owned());
        let observed = graph.observe(file.clone(), InputValue::Bytes(Ok(bytes.into())));
        reads.dependencies.insert(file, observed);
        for (key, value) in [
            (InputKey::Exists(path.to_owned()), InputValue::Bool(true)),
            (
                InputKey::TryExists(path.to_owned()),
                InputValue::Identity(Ok(true)),
            ),
            (InputKey::IsFile(path.to_owned()), InputValue::Bool(true)),
            (InputKey::IsDir(path.to_owned()), InputValue::Bool(false)),
        ] {
            if let Some(expected) = reads.dependencies.get_mut(&key) {
                *expected = graph.observe(key, value);
            }
        }
    }

    /// Declare executable lookup as an input of a compiler probe.
    pub(crate) fn executable(
        &self,
        program: &Path,
        cwd: &Path,
        search_path: &OsStr,
    ) -> Option<PathBuf> {
        let key = InputKey::Executable {
            program: program.to_owned(),
            cwd: cwd.to_owned(),
            search_path: search_path.to_owned(),
        };
        let value = key.evaluate();
        let result = match &value {
            InputValue::Executable(Ok((path, _))) => Some(path.clone()),
            _ => None,
        };
        self.record(key, value);
        result
    }

    /// Declare the selected installation before executing compiler queries.
    pub(crate) fn compiler_installation(&self, root: &Path) -> bool {
        let key = InputKey::CompilerInstallation(root.to_owned());
        let value = key.evaluate();
        let valid = matches!(value, InputValue::Installation(Ok(_)));
        self.record(key, value);
        valid
    }

    /// Record native libraries available in a compiler loader search directory.
    pub(crate) fn compiler_library_directory(&self, directory: &Path) -> bool {
        let key = InputKey::CompilerLibraryDirectory(directory.to_owned());
        let value = key.evaluate();
        let valid = matches!(value, InputValue::Installation(Ok(_)));
        self.record(key, value);
        valid
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum InputKey {
    File(PathBuf),
    Exists(PathBuf),
    TryExists(PathBuf),
    IsFile(PathBuf),
    IsDir(PathBuf),
    EntryType(PathBuf),
    Directory(PathBuf),
    Glob(String),
    Canonical(PathBuf),
    SameFile(PathBuf, PathBuf),
    Executable {
        program: PathBuf,
        cwd: PathBuf,
        search_path: OsString,
    },
    CompilerInstallation(PathBuf),
    CompilerLibraryDirectory(PathBuf),
}

impl std::fmt::Display for InputKey {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::File(path) => write!(f, "contents of {}", path.display()),
            Self::Exists(path)
            | Self::TryExists(path)
            | Self::IsFile(path)
            | Self::IsDir(path)
            | Self::EntryType(path) => {
                write!(f, "path type of {}", path.display())
            }
            Self::Directory(path) => write!(f, "directory entries in {}", path.display()),
            Self::Glob(pattern) => write!(f, "workspace glob {pattern:?}"),
            Self::Canonical(path) => write!(f, "canonical path of {}", path.display()),
            Self::SameFile(a, b) => {
                write!(f, "file identity of {} and {}", a.display(), b.display())
            }
            Self::Executable { program, .. } => write!(f, "executable {}", program.display()),
            Self::CompilerInstallation(path) => {
                write!(f, "compiler installation {}", path.display())
            }
            Self::CompilerLibraryDirectory(path) => {
                write!(f, "compiler library search directory {}", path.display())
            }
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum InputValue {
    Bytes(Result<Arc<[u8]>, io::ErrorKind>),
    Bool(bool),
    Type(Result<PathType, io::ErrorKind>),
    Directory(Result<Vec<Result<OsString, io::ErrorKind>>, io::ErrorKind>),
    Paths(Result<Vec<PathBuf>, String>),
    Path(Result<PathBuf, io::ErrorKind>),
    Identity(Result<bool, io::ErrorKind>),
    Executable(Result<(PathBuf, FileIdentity), io::ErrorKind>),
    Installation(Result<Vec<(PathBuf, FileIdentity)>, String>),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PathType {
    File,
    Directory,
    Symlink,
    Other,
}

impl From<fs::FileType> for PathType {
    fn from(value: fs::FileType) -> Self {
        if value.is_file() {
            Self::File
        } else if value.is_dir() {
            Self::Directory
        } else if value.is_symlink() {
            Self::Symlink
        } else {
            Self::Other
        }
    }
}

fn io_value<T>(value: io::Result<T>) -> Result<T, io::ErrorKind> {
    value.map_err(|error| error.kind())
}

fn glob_paths(pattern: &str) -> CargoResult<Vec<PathBuf>> {
    let paths =
        glob::glob(pattern).with_context(|| format!("could not parse pattern `{pattern}`"))?;
    let mut paths = paths
        .map(|path| path.with_context(|| format!("unable to match path to pattern `{pattern}`")))
        .collect::<Result<Vec<_>, _>>()?;
    paths.sort();
    Ok(paths)
}

fn directory_value(entries: &[io::Result<fs::DirEntry>]) -> InputValue {
    let mut names = entries
        .iter()
        .map(|entry| {
            entry
                .as_ref()
                .map(fs::DirEntry::file_name)
                .map_err(io::Error::kind)
        })
        .collect::<Vec<_>>();
    // Errors do not implement Ord; filenames are the meaningful ordering.
    names.sort_by(|a, b| a.as_ref().ok().cmp(&b.as_ref().ok()));
    InputValue::Directory(Ok(names))
}

impl InputKey {
    fn evaluate(&self) -> InputValue {
        match self {
            Self::File(path) => InputValue::Bytes(io_value(fs::read(path).map(Arc::from))),
            Self::Exists(path) => InputValue::Bool(path.exists()),
            Self::TryExists(path) => InputValue::Identity(io_value(path.try_exists())),
            Self::IsFile(path) => InputValue::Bool(path.is_file()),
            Self::IsDir(path) => InputValue::Bool(path.is_dir()),
            Self::EntryType(path) => InputValue::Type(io_value(
                fs::symlink_metadata(path).map(|meta| meta.file_type().into()),
            )),
            Self::Directory(path) => match fs::read_dir(path) {
                Ok(entries) => directory_value(&entries.collect::<Vec<_>>()),
                Err(error) => InputValue::Directory(Err(error.kind())),
            },
            Self::Glob(pattern) => {
                InputValue::Paths(glob_paths(pattern).map_err(|e| e.to_string()))
            }
            Self::Canonical(path) => InputValue::Path(io_value(fs::canonicalize(path))),
            Self::SameFile(a, b) => InputValue::Identity(io_value(same_file::is_same_file(a, b))),
            Self::Executable {
                program,
                cwd,
                search_path,
            } => InputValue::Executable(io_value(resolve_executable(program, cwd, search_path))),
            Self::CompilerInstallation(root) => {
                InputValue::Installation(installation(root).map_err(|e| e.to_string()))
            }
            Self::CompilerLibraryDirectory(directory) => {
                InputValue::Installation(library_directory(directory).map_err(|e| e.to_string()))
            }
        }
    }
}

/// Cargo's ordinary filesystem operations, optionally observed by an epoch.
#[derive(Clone, Copy)]
pub(crate) struct TrackedFs<'a> {
    tracker: Option<&'a InputTracker>,
}

impl<'a> TrackedFs<'a> {
    pub(crate) fn new(tracker: Option<&'a InputTracker>) -> Self {
        Self { tracker }
    }

    pub(crate) fn read(&self, path: &Path) -> io::Result<Vec<u8>> {
        let result = fs::read(path);
        if let Some(tracker) = self.tracker {
            tracker.record(
                InputKey::File(path.to_owned()),
                InputValue::Bytes(
                    result
                        .as_ref()
                        .map(|b| Arc::from(b.as_slice()))
                        .map_err(io::Error::kind),
                ),
            );
        }
        result
    }

    pub(crate) fn read_to_string(&self, path: &Path) -> io::Result<String> {
        if self.tracker.is_none() {
            return fs::read_to_string(path);
        }
        String::from_utf8(self.read(path)?).map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "stream did not contain valid UTF-8",
            )
        })
    }

    pub(crate) fn exists(&self, path: &Path) -> bool {
        let value = path.exists();
        if let Some(tracker) = self.tracker {
            tracker.record(InputKey::Exists(path.to_owned()), InputValue::Bool(value));
        }
        value
    }

    pub(crate) fn try_exists(&self, path: &Path) -> io::Result<bool> {
        let result = path.try_exists();
        if let Some(tracker) = self.tracker {
            tracker.record(
                InputKey::TryExists(path.to_owned()),
                InputValue::Identity(result.as_ref().copied().map_err(io::Error::kind)),
            );
        }
        result
    }

    pub(crate) fn is_file(&self, path: &Path) -> bool {
        let value = path.is_file();
        if let Some(tracker) = self.tracker {
            tracker.record(InputKey::IsFile(path.to_owned()), InputValue::Bool(value));
        }
        value
    }

    pub(crate) fn is_dir(&self, path: &Path) -> bool {
        let value = path.is_dir();
        if let Some(tracker) = self.tracker {
            tracker.record(InputKey::IsDir(path.to_owned()), InputValue::Bool(value));
        }
        value
    }

    pub(crate) fn canonicalize(&self, path: &Path) -> io::Result<PathBuf> {
        let result = fs::canonicalize(path);
        if let Some(tracker) = self.tracker {
            tracker.record(
                InputKey::Canonical(path.to_owned()),
                InputValue::Path(result.as_ref().cloned().map_err(io::Error::kind)),
            );
        }
        result
    }

    pub(crate) fn same_file(&self, a: &Path, b: &Path) -> io::Result<bool> {
        let result = same_file::is_same_file(a, b);
        if let Some(tracker) = self.tracker {
            tracker.record(
                InputKey::SameFile(a.to_owned(), b.to_owned()),
                InputValue::Identity(result.as_ref().copied().map_err(io::Error::kind)),
            );
        }
        result
    }

    pub(crate) fn glob(&self, pattern: &str) -> CargoResult<Vec<PathBuf>> {
        let result = glob_paths(pattern);
        if let Some(tracker) = self.tracker {
            tracker.record(
                InputKey::Glob(pattern.to_owned()),
                InputValue::Paths(result.as_ref().cloned().map_err(ToString::to_string)),
            );
        }
        result
    }

    pub(crate) fn read_dir(&self, path: &Path) -> io::Result<ReadDir<'a>> {
        let Some(tracker) = self.tracker else {
            return Ok(ReadDir {
                entries: DirectoryIter::Live(fs::read_dir(path)?),
                tracker: None,
            });
        };
        let entries = fs::read_dir(path).map(|entries| entries.collect::<Vec<_>>());
        tracker.record(
            InputKey::Directory(path.to_owned()),
            match &entries {
                Ok(entries) => directory_value(entries),
                Err(error) => InputValue::Directory(Err(error.kind())),
            },
        );
        Ok(ReadDir {
            entries: DirectoryIter::Observed(entries?.into_iter()),
            tracker: Some(tracker),
        })
    }
}

pub(crate) struct ReadDir<'a> {
    entries: DirectoryIter,
    tracker: Option<&'a InputTracker>,
}

enum DirectoryIter {
    Live(fs::ReadDir),
    Observed(std::vec::IntoIter<io::Result<fs::DirEntry>>),
}

impl<'a> Iterator for ReadDir<'a> {
    type Item = io::Result<DirEntry<'a>>;
    fn next(&mut self) -> Option<Self::Item> {
        let next = match &mut self.entries {
            DirectoryIter::Live(entries) => entries.next(),
            DirectoryIter::Observed(entries) => entries.next(),
        };
        next.map(|entry| {
            entry.map(|inner| DirEntry {
                inner,
                tracker: self.tracker,
            })
        })
    }
}

pub(crate) struct DirEntry<'a> {
    inner: fs::DirEntry,
    tracker: Option<&'a InputTracker>,
}

impl DirEntry<'_> {
    pub(crate) fn path(&self) -> PathBuf {
        self.inner.path()
    }
    pub(crate) fn file_name(&self) -> OsString {
        self.inner.file_name()
    }
    pub(crate) fn file_type(&self) -> io::Result<fs::FileType> {
        let result = self.inner.file_type();
        if let Some(tracker) = self.tracker {
            tracker.record(
                InputKey::EntryType(self.path()),
                InputValue::Type(
                    result
                        .as_ref()
                        .map(|kind| (*kind).into())
                        .map_err(io::Error::kind),
                ),
            );
        }
        result
    }
}

// External compiler queries have an explicit filesystem closure. We compare
// identity (including ctime on Unix) for installed artifacts, not source bytes.
#[derive(Clone, Debug, Eq, PartialEq)]
struct FileIdentity {
    len: u64,
    modified: Option<std::time::SystemTime>,
    kind: PathType,
    canonical: PathBuf,
    #[cfg(unix)]
    unix: (u64, u64, i64, i64, u32),
}

impl FileIdentity {
    fn from_metadata(metadata: &fs::Metadata, canonical: PathBuf) -> Self {
        #[cfg(unix)]
        use std::os::unix::fs::MetadataExt;
        Self {
            len: metadata.len(),
            modified: metadata.modified().ok(),
            kind: metadata.file_type().into(),
            canonical,
            #[cfg(unix)]
            unix: (
                metadata.dev(),
                metadata.ino(),
                metadata.ctime(),
                metadata.ctime_nsec(),
                metadata.mode(),
            ),
        }
    }
}

fn identity(path: &Path) -> io::Result<FileIdentity> {
    let metadata = fs::metadata(path)?;
    Ok(FileIdentity::from_metadata(
        &metadata,
        fs::canonicalize(path)?,
    ))
}

fn resolve_executable(
    program: &Path,
    cwd: &Path,
    search_path: &OsStr,
) -> io::Result<(PathBuf, FileIdentity)> {
    let candidates = if program.components().count() > 1 || program.is_absolute() {
        vec![cwd.join(program)]
    } else {
        std::env::split_paths(search_path)
            .map(|dir| cwd.join(dir).join(program))
            .collect()
    };
    for candidate in candidates {
        let Ok(meta) = fs::metadata(&candidate) else {
            continue;
        };
        if !meta.is_file() {
            continue;
        }
        let stamp = identity(&candidate)?;
        return Ok((stamp.canonical.clone(), stamp));
    }
    Err(io::ErrorKind::NotFound.into())
}

fn installation(root: &Path) -> CargoResult<Vec<(PathBuf, FileIdentity)>> {
    installation_with(root, identity, |_| {})
}

/// Report visited directories alongside the ordinary installation snapshot.
fn installation_with(
    root: &Path,
    mut identify: impl FnMut(&Path) -> io::Result<FileIdentity>,
    mut directory: impl FnMut(&Path),
) -> CargoResult<Vec<(PathBuf, FileIdentity)>> {
    let compiler = root
        .join("bin")
        .join(format!("rustc{}", std::env::consts::EXE_SUFFIX));
    let mut values = vec![(compiler.clone(), identify(&compiler)?)];
    for entry in walkdir::WalkDir::new(root.join("lib")).follow_links(true) {
        let entry = entry?;
        if entry.file_type().is_dir() {
            directory(entry.path());
        }
        let path = entry.into_path();
        values.push((path.clone(), identify(&path)?));
    }
    values.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(values)
}

/// Snapshot loadable native libraries without depending on unrelated build outputs.
fn library_directory(directory: &Path) -> CargoResult<Vec<(PathBuf, FileIdentity)>> {
    library_directory_with(directory, identity, |_| {})
}

/// Collect every visited directory, including directories with no native libraries.
fn library_directory_with(
    directory: &Path,
    mut identify: impl FnMut(&Path) -> io::Result<FileIdentity>,
    mut visited_directory: impl FnMut(&Path),
) -> CargoResult<Vec<(PathBuf, FileIdentity)>> {
    match fs::metadata(directory) {
        Ok(metadata) if metadata.is_dir() => {}
        Ok(_) => return Ok(Vec::new()),
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
            ) =>
        {
            return Ok(Vec::new());
        }
        Err(error) => return Err(error.into()),
    }
    let mut libraries = Vec::new();
    for entry in walkdir::WalkDir::new(directory).follow_links(true) {
        let entry = entry?;
        if entry.file_type().is_dir() {
            visited_directory(entry.path());
        }
        if !entry.file_type().is_file() {
            continue;
        }
        let name = entry.file_name().as_encoded_bytes();
        if is_non_native_artifact(name) {
            continue;
        }
        let native_library = if cfg!(target_os = "macos") {
            name.ends_with(b".dylib")
                || entry.path().components().any(|component| {
                    component
                        .as_os_str()
                        .as_encoded_bytes()
                        .ends_with(b".framework")
                })
        } else {
            name.windows(3).any(|part| part == b".so")
        };
        if native_library {
            let path = entry.into_path();
            libraries.push((path.clone(), identify(&path)?));
        }
    }
    // Traverse loader subdirectories such as glibc-hwcaps and framework bundles,
    // but exclude directory metadata so empty directories and build outputs
    // cannot invalidate a lookup. Canonical file identities include symlink targets.
    libraries.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(libraries)
}

fn is_non_native_artifact(name: &[u8]) -> bool {
    [b".rlib".as_slice(), b".rmeta".as_slice(), b".d".as_slice()]
        .iter()
        .any(|suffix| name.ends_with(suffix))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn equal_contents_survive_atomic_replacement() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("Cargo.toml");
        fs::write(&path, "old").unwrap();
        let tracker = SessionInputs::default().begin();
        assert_eq!(TrackedFs::new(Some(&tracker)).read(&path).unwrap(), b"old");
        let replacement = dir.path().join("replacement");
        fs::write(&replacement, "old").unwrap();
        fs::rename(&replacement, &path).unwrap();
        tracker.validate().unwrap();
        let graph = tracker.graph.lock().unwrap();
        let node = &graph.nodes[&InputKey::File(path.clone())];
        assert!(node.changed_at < node.verified_at);
        drop(graph);
        fs::write(&path, "new").unwrap();
        assert!(tracker.validate().is_err());
    }

    #[test]
    fn absence_and_directory_membership_are_dependencies() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("optional.toml");
        let tracker = SessionInputs::default().begin();
        let files = TrackedFs::new(Some(&tracker));
        assert!(!files.exists(&path));
        assert_eq!(files.read_dir(dir.path()).unwrap().count(), 0);
        tracker.validate().unwrap();
        fs::write(&path, "").unwrap();
        assert!(tracker.validate().is_err());
    }

    #[test]
    fn conflicting_reads_cannot_be_blessed_by_later_validation_or_publication() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("Cargo.lock");
        let tracker = SessionInputs::default().begin();
        tracker.observe_file(&path, b"first");
        tracker.observe_file(&path, b"second");
        fs::write(&path, "second").unwrap();
        tracker.publish_file(&path, b"second");
        assert!(
            tracker
                .validate()
                .unwrap_err()
                .to_string()
                .contains("inconsistent reads")
        );
    }

    #[test]
    fn authored_lockfile_is_published_but_external_edit_is_not() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("Cargo.lock");
        let tracker = SessionInputs::default().begin();
        assert!(!TrackedFs::new(Some(&tracker)).exists(&path));
        tracker.observe_missing_file(&path);
        fs::write(&path, "generated").unwrap();
        tracker.publish_file(&path, b"generated");
        tracker.validate().unwrap();
        fs::write(&path, "changed concurrently").unwrap();
        assert!(tracker.validate().is_err());
        fs::write(&path, "authored after invalidation").unwrap();
        tracker.publish_file(&path, b"authored after invalidation");
        assert!(tracker.validate().is_err());
    }

    #[test]
    fn a_new_epoch_retires_previous_trackers() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("Cargo.lock");
        let session = SessionInputs::default();
        let old = session.begin();
        old.observe_file(&path, b"old");

        let current = session.begin();
        fs::write(&path, "current").unwrap();
        current.observe_file(&path, b"current");
        let revision = current.revision();
        assert!(old.validate().unwrap_err().to_string().contains("retired"));
        old.observe_file(&path, b"stale read");
        old.observe_missing_file(&dir.path().join("stale node"));
        old.publish_file(&path, b"stale write");
        assert!(old.validate().is_err());

        assert_eq!(current.revision(), revision);
        assert_eq!(current.graph.lock().unwrap().nodes.len(), 1);
        current.validate().unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn library_lookup_ignores_artifacts_but_tracks_new_native_libraries() {
        use std::os::unix::ffi::OsStringExt;

        let dir = tempfile::tempdir().unwrap();
        let directory = dir.path().join("libraries");
        let tracker = SessionInputs::default().begin();
        assert!(tracker.compiler_library_directory(&directory));
        fs::write(&directory, "not a directory").unwrap();
        assert!(tracker.compiler_library_directory(&directory));
        fs::remove_file(&directory).unwrap();
        fs::create_dir(&directory).unwrap();
        for artifact in [
            "libignored.so.rlib",
            "libignored.so.rmeta",
            "libignored.so.d",
        ] {
            fs::write(directory.join(artifact), "artifact").unwrap();
        }
        tracker.validate().unwrap();

        let nested = directory.join("glibc-hwcaps/x86-64-v3");
        fs::create_dir_all(&nested).unwrap();
        fs::write(nested.join("libignored.so.rlib"), "artifact").unwrap();
        tracker.validate().unwrap();
        let native = if cfg!(target_os = "macos") {
            // The macOS CI filesystem rejects non-UTF-8 filenames.
            b"libshadow.dylib".as_slice()
        } else {
            b"libshadow\xff.so.1".as_slice()
        };
        fs::write(nested.join(OsString::from_vec(native.to_vec())), "library").unwrap();
        assert!(tracker.validate().is_err());
    }

    #[cfg(unix)]
    #[test]
    fn symlink_retargeting_invalidates_canonical_paths() {
        use std::os::unix::fs::symlink;
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("a");
        let b = dir.path().join("b");
        let link = dir.path().join("link");
        fs::create_dir(&a).unwrap();
        fs::create_dir(&b).unwrap();
        symlink(&a, &link).unwrap();
        let tracker = SessionInputs::default().begin();
        assert_eq!(
            TrackedFs::new(Some(&tracker)).canonicalize(&link).unwrap(),
            a.canonicalize().unwrap()
        );
        fs::remove_file(&link).unwrap();
        symlink(&b, &link).unwrap();
        assert!(tracker.validate().is_err());
    }
}
