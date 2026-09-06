//! Reuse topology while continuing to poll file bytes and artifact identities.

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsStr;
use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;

use crate::util::data_structures::HashMap;

use super::watcher::{Token, Watcher};
use super::{FileIdentity, InputKey, InputValue};

#[derive(Debug, Default)]
pub(super) struct InputCache {
    watcher: Watcher,
    canonical: HashMap<PathBuf, Arc<CachedCanonical>>,
    topology: BTreeMap<InputKey, Arc<CachedTopology>>,
    #[cfg(test)]
    pub(super) last_stats: Stats,
    #[cfg(test)]
    before_tree_coverage: Option<fn(&InputKey)>,
    #[cfg(test)]
    after_pass: Option<fn(&InputKey)>,
}

#[cfg(test)]
#[derive(Clone, Copy, Debug, Default)]
pub(super) struct Stats {
    pub(super) metadata_reads: usize,
    pub(super) canonical_reads: usize,
    pub(super) directory_reads: usize,
    pub(super) tree_scans: usize,
    pub(super) cache_hits: usize,
    pub(super) fallback_passes: usize,
}

#[derive(Debug)]
struct CachedCanonical {
    path: PathBuf,
    coverage: Coverage,
}

#[derive(Debug)]
struct CachedTopology {
    value: TopologyValue,
    coverage: Coverage,
}

#[derive(Debug)]
enum TopologyValue {
    Directory(InputValue),
    Tree(Vec<PathBuf>),
}

/// Changes to directory contents are covered by notifications. Structural
/// guards catch replacement and mount changes without treating unrelated
/// sibling writes as changes to path resolution.
#[derive(Clone, Debug, Eq, PartialEq)]
struct StructuralIdentity {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
}

impl StructuralIdentity {
    fn new(metadata: &fs::Metadata) -> Self {
        Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            mode: metadata.mode(),
            uid: metadata.uid(),
            gid: metadata.gid(),
        }
    }
}

#[derive(Debug, Default)]
struct Coverage {
    tokens: Vec<Token>,
    paths: HashMap<PathBuf, StructuralIdentity>,
    links: HashMap<PathBuf, PathBuf>,
}

impl Coverage {
    /// Arm each parent before observing the next component. Follow link targets
    /// explicitly so intermediate links omitted by canonicalize are covered too.
    fn path(&mut self, watcher: &mut Watcher, path: &Path) -> Option<()> {
        if !path.is_absolute() || path.components().any(|part| part == Component::ParentDir) {
            return None;
        }
        // A trailing separator or `.` can make symlink_metadata follow the
        // final link. Inspect normalized components while keeping the original
        // query spelling for the authoritative filesystem operation.
        let path = path.components().collect::<PathBuf>();
        // A successful canonicalization cannot require arbitrarily many links.
        // Limit cache setup independently from Cargo's actual filesystem query.
        if self.links.len() > 64 {
            return None;
        }
        let ancestors = path.ancestors().collect::<Vec<_>>();
        for component in ancestors.into_iter().rev() {
            if self.paths.contains_key(component) {
                continue;
            }
            let token = match component.parent() {
                Some(parent) => watcher.observe(parent, Some(component.file_name()?))?,
                None => watcher.observe(component, Some(OsStr::new("")))?,
            };
            self.tokens.push(token);
            // Setup must not reuse an observation made before its watch was armed.
            let metadata = fs::symlink_metadata(component).ok()?;
            self.paths
                .insert(component.to_owned(), StructuralIdentity::new(&metadata));
            if metadata.file_type().is_symlink() {
                let target = fs::read_link(component).ok()?;
                self.links.insert(component.to_owned(), target.clone());
                let target = component.parent()?.join(target);
                self.path(watcher, &target)?;
            }
        }
        Some(())
    }

    fn directory(&mut self, watcher: &mut Watcher, directory: &Path) -> Option<()> {
        self.path(watcher, directory)?;
        self.tokens.push(watcher.observe(directory, None)?);
        Some(())
    }
}

#[derive(Debug)]
struct IoFailure {
    kind: io::ErrorKind,
    raw: Option<i32>,
    message: String,
}

impl IoFailure {
    fn new(error: io::Error) -> Self {
        Self {
            kind: error.kind(),
            raw: error.raw_os_error(),
            message: error.to_string(),
        }
    }

    fn error(&self) -> io::Error {
        self.raw.map_or_else(
            || io::Error::new(self.kind, self.message.clone()),
            io::Error::from_raw_os_error,
        )
    }
}

struct Pass<'a> {
    cache: &'a mut InputCache,
    metadata: HashMap<PathBuf, Result<fs::Metadata, IoFailure>>,
    symlink_metadata: HashMap<PathBuf, Result<fs::Metadata, IoFailure>>,
    links: HashMap<PathBuf, Result<PathBuf, IoFailure>>,
    used: Vec<Token>,
    #[cfg(test)]
    stats: Stats,
}

impl InputCache {
    /// Synchronize before and after using cached topology. If coverage changed
    /// during this pass, discard its results and perform one complete poll.
    pub(super) fn evaluate(&mut self, keys: &[&InputKey]) -> Vec<InputValue> {
        self.watcher.synchronize();
        let mut pass = Pass {
            cache: self,
            metadata: HashMap::default(),
            symlink_metadata: HashMap::default(),
            links: HashMap::default(),
            used: Vec::new(),
            #[cfg(test)]
            stats: Stats::default(),
        };
        let values = keys.iter().map(|key| pass.evaluate(key)).collect();
        #[cfg(test)]
        if let Some(hook) = pass.cache.after_pass.take()
            && let Some(key) = keys.first()
        {
            hook(key);
        }
        pass.cache.watcher.synchronize();
        let stable = pass
            .used
            .iter()
            .all(|token| pass.cache.watcher.unchanged(token));
        #[cfg(test)]
        {
            pass.cache.last_stats = pass.stats;
        }
        if stable {
            values
        } else {
            // A fresh poll has the same non-atomic snapshot contract as ordinary
            // validation. It never depends on potentially stale cached topology.
            #[cfg(test)]
            {
                pass.cache.last_stats.fallback_passes += 1;
            }
            keys.iter().map(|key| key.evaluate()).collect()
        }
    }

    #[cfg(test)]
    pub(super) fn simulate_overflow(&mut self) {
        self.watcher.simulate_overflow();
    }

    #[cfg(test)]
    pub(super) fn simulate_failure(&mut self) {
        self.watcher.simulate_failure();
    }
}

impl Pass<'_> {
    fn evaluate(&mut self, key: &InputKey) -> InputValue {
        match key {
            // Byte contents always remain authoritative, including mmap writes
            // that need not produce a notification.
            InputKey::File(_) => key.evaluate(),
            InputKey::Exists(path) => InputValue::Bool(self.metadata(path).is_ok()),
            InputKey::IsFile(path) => {
                InputValue::Bool(self.metadata(path).is_ok_and(|metadata| metadata.is_file()))
            }
            InputKey::IsDir(path) => {
                InputValue::Bool(self.metadata(path).is_ok_and(|metadata| metadata.is_dir()))
            }
            InputKey::EntryType(path) => InputValue::Type(super::io_value(
                self.symlink_metadata(path)
                    .map(|metadata| metadata.file_type().into()),
            )),
            InputKey::Canonical(path) => InputValue::Path(super::io_value(self.canonical(path))),
            InputKey::Directory(path) => self.directory(key, path),
            InputKey::CompilerInstallation(_) | InputKey::CompilerLibraryDirectory(_) => {
                self.tree(key)
            }
            InputKey::Executable {
                program,
                cwd,
                search_path,
            } => {
                InputValue::Executable(super::io_value(self.executable(program, cwd, search_path)))
            }
            // Preserve the exact operation for errors, general globs, and
            // same-file handles until they have an equally complete contract.
            InputKey::TryExists(_) | InputKey::Glob(_) | InputKey::SameFile(_, _) => key.evaluate(),
        }
    }

    fn metadata(&mut self, path: &Path) -> io::Result<fs::Metadata> {
        if !self.metadata.contains_key(path) {
            #[cfg(test)]
            {
                self.stats.metadata_reads += 1;
            }
            self.metadata
                .insert(path.to_owned(), fs::metadata(path).map_err(IoFailure::new));
        }
        self.metadata[path]
            .as_ref()
            .cloned()
            .map_err(IoFailure::error)
    }

    fn symlink_metadata(&mut self, path: &Path) -> io::Result<fs::Metadata> {
        if !self.symlink_metadata.contains_key(path) {
            #[cfg(test)]
            {
                self.stats.metadata_reads += 1;
            }
            self.symlink_metadata.insert(
                path.to_owned(),
                fs::symlink_metadata(path).map_err(IoFailure::new),
            );
        }
        self.symlink_metadata[path]
            .as_ref()
            .cloned()
            .map_err(IoFailure::error)
    }

    fn read_link(&mut self, path: &Path) -> io::Result<PathBuf> {
        self.links
            .entry(path.to_owned())
            .or_insert_with(|| fs::read_link(path).map_err(IoFailure::new))
            .as_ref()
            .cloned()
            .map_err(IoFailure::error)
    }

    fn covered(&mut self, coverage: &Coverage) -> bool {
        if !coverage
            .tokens
            .iter()
            .all(|token| self.cache.watcher.unchanged(token))
        {
            return false;
        }
        for (path, expected) in &coverage.paths {
            if !self
                .symlink_metadata(path)
                .is_ok_and(|metadata| StructuralIdentity::new(&metadata) == *expected)
            {
                return false;
            }
        }
        for (path, expected) in &coverage.links {
            if !self.read_link(path).is_ok_and(|target| target == *expected) {
                return false;
            }
        }
        self.used.extend(coverage.tokens.iter().cloned());
        #[cfg(test)]
        {
            self.stats.cache_hits += 1;
        }
        true
    }

    fn canonical(&mut self, path: &Path) -> io::Result<PathBuf> {
        let cached = self.cache.canonical.get(path).cloned();
        if let Some(cached) = cached
            && self.covered(&cached.coverage)
        {
            return Ok(cached.path.clone());
        }
        #[cfg(test)]
        {
            self.stats.canonical_reads += 1;
        }
        let canonical = fs::canonicalize(path)?;
        let mut coverage = Coverage::default();
        if coverage.path(&mut self.cache.watcher, path).is_none() {
            return Ok(canonical);
        }
        // Failed queries stay on the polling path without opening every
        // ancestor. For successful queries, repeat after arming the watches.
        #[cfg(test)]
        {
            self.stats.canonical_reads += 1;
        }
        let canonical = fs::canonicalize(path)?;
        self.used.extend(coverage.tokens.iter().cloned());
        self.cache.canonical.insert(
            path.to_owned(),
            Arc::new(CachedCanonical {
                path: canonical.clone(),
                coverage,
            }),
        );
        Ok(canonical)
    }

    fn identity(&mut self, path: &Path) -> io::Result<FileIdentity> {
        let metadata = self.metadata(path)?;
        let canonical = self.canonical(path)?;
        Ok(FileIdentity::from_metadata(&metadata, canonical))
    }

    fn executable(
        &mut self,
        program: &Path,
        cwd: &Path,
        search_path: &OsStr,
    ) -> io::Result<(PathBuf, FileIdentity)> {
        let candidates = if program.components().count() > 1 || program.is_absolute() {
            vec![cwd.join(program)]
        } else {
            std::env::split_paths(search_path)
                .map(|directory| cwd.join(directory).join(program))
                .collect()
        };
        for candidate in candidates {
            if !self
                .metadata(&candidate)
                .is_ok_and(|metadata| metadata.is_file())
            {
                continue;
            }
            let stamp = self.identity(&candidate)?;
            return Ok((stamp.canonical.clone(), stamp));
        }
        Err(io::ErrorKind::NotFound.into())
    }

    fn directory(&mut self, key: &InputKey, path: &Path) -> InputValue {
        let cached = self.cache.topology.get(key).cloned();
        if let Some(cached) = cached
            && let TopologyValue::Directory(value) = &cached.value
            && self.covered(&cached.coverage)
        {
            return value.clone();
        }
        #[cfg(test)]
        {
            self.stats.directory_reads += 1;
        }
        let value = key.evaluate();
        if !matches!(value, InputValue::Directory(Ok(ref entries)) if entries.iter().all(Result::is_ok))
        {
            return value;
        }
        let mut coverage = Coverage::default();
        if coverage.directory(&mut self.cache.watcher, path).is_none() {
            return value;
        }
        #[cfg(test)]
        {
            self.stats.directory_reads += 1;
        }
        let value = key.evaluate();
        if matches!(value, InputValue::Directory(Ok(ref entries)) if entries.iter().all(Result::is_ok))
        {
            self.used.extend(coverage.tokens.iter().cloned());
            self.cache.topology.insert(
                key.clone(),
                Arc::new(CachedTopology {
                    value: TopologyValue::Directory(value.clone()),
                    coverage,
                }),
            );
        }
        value
    }

    fn scan(&mut self, key: &InputKey) -> (InputValue, BTreeSet<PathBuf>) {
        #[cfg(test)]
        {
            self.stats.tree_scans += 1;
        }
        let mut directories = BTreeSet::new();
        let value = match key {
            InputKey::CompilerInstallation(root) => super::installation_with(
                root,
                |path| self.identity(path),
                |path| {
                    directories.insert(path.to_owned());
                },
            ),
            InputKey::CompilerLibraryDirectory(root) => super::library_directory_with(
                root,
                |path| self.identity(path),
                |path| {
                    directories.insert(path.to_owned());
                },
            ),
            _ => unreachable!("only compiler trees have enumeration snapshots"),
        };
        (
            InputValue::Installation(value.map_err(|error| error.to_string())),
            directories,
        )
    }

    fn tree(&mut self, key: &InputKey) -> InputValue {
        let cached = self.cache.topology.get(key).cloned();
        if let Some(cached) = cached
            && let TopologyValue::Tree(paths) = &cached.value
            && self.covered(&cached.coverage)
        {
            let values = paths
                .iter()
                .map(|path| self.identity(path).map(|identity| (path.clone(), identity)))
                .collect::<io::Result<Vec<_>>>();
            return InputValue::Installation(values.map_err(|error| error.to_string()));
        }
        let (value, directories) = self.scan(key);
        if !matches!(value, InputValue::Installation(Ok(_))) || directories.is_empty() {
            return value;
        }
        #[cfg(test)]
        if let Some(hook) = self.cache.before_tree_coverage.take() {
            hook(key);
        }
        let mut coverage = Coverage::default();
        if !directories.iter().all(|directory| {
            coverage
                .directory(&mut self.cache.watcher, directory)
                .is_some()
        }) {
            return value;
        }
        // The first walk discovered what to watch. Repeat with watches armed;
        // a new directory must not enter the cache without its own coverage.
        let (value, current_directories) = self.scan(key);
        if current_directories == directories
            && let InputValue::Installation(Ok(values)) = &value
        {
            self.used.extend(coverage.tokens.iter().cloned());
            self.cache.topology.insert(
                key.clone(),
                Arc::new(CachedTopology {
                    value: TopologyValue::Tree(
                        values.iter().map(|(path, _)| path.clone()).collect(),
                    ),
                    coverage,
                }),
            );
        }
        value
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::symlink;

    fn evaluate(cache: &mut InputCache, keys: &[InputKey]) -> Vec<InputValue> {
        cache.evaluate(&keys.iter().collect::<Vec<_>>())
    }

    fn polled(keys: &[InputKey]) -> Vec<InputValue> {
        keys.iter().map(InputKey::evaluate).collect()
    }

    fn watched_tempdir() -> Option<tempfile::TempDir> {
        let dir = tempfile::tempdir().unwrap();
        let mut watcher = Watcher::default();
        watcher.synchronize();
        Coverage::default()
            .directory(&mut watcher, dir.path())
            .map(|()| dir)
    }

    #[test]
    fn negative_and_parent_queries_do_not_arm_watches() {
        let dir = tempfile::tempdir().unwrap();
        fs::create_dir(dir.path().join("child")).unwrap();
        let missing = dir.path().join("missing");
        let keys = [
            InputKey::Canonical(missing.clone()),
            InputKey::Directory(missing.clone()),
            InputKey::Canonical(dir.path().join("child/..")),
        ];
        let mut cache = InputCache::default();
        for _ in 0..2 {
            assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
            assert_eq!(cache.watcher.watch_count(), 0);
        }
        fs::create_dir(&missing).unwrap();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        fs::write(missing.join("new"), "file").unwrap();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
    }

    #[test]
    fn unchanged_trees_skip_walks_and_canonicalization_but_poll_identities() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let root = dir.path();
        fs::create_dir(root.join("bin")).unwrap();
        fs::create_dir_all(root.join("lib/glibc-hwcaps/level")).unwrap();
        fs::write(root.join("bin/rustc"), "compiler").unwrap();
        fs::write(root.join("lib/libone.so.1"), "library").unwrap();
        fs::write(root.join("lib/glibc-hwcaps/level/libtwo.so"), "library").unwrap();
        let keys = [
            InputKey::CompilerInstallation(root.to_owned()),
            InputKey::CompilerLibraryDirectory(root.join("lib")),
            InputKey::Directory(root.join("lib")),
            InputKey::Canonical(root.join("bin/rustc")),
        ];
        let mut cache = InputCache::default();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert_eq!(cache.last_stats.tree_scans, 0);
        assert_eq!(cache.last_stats.directory_reads, 0);
        assert_eq!(cache.last_stats.canonical_reads, 0);
        assert!(cache.last_stats.metadata_reads > 0);
        assert!(cache.last_stats.cache_hits > 0);

        // A quiet notification queue does not replace the identity metadata poll.
        let library = root.join("lib/libone.so.1");
        filetime::set_file_mtime(&library, filetime::FileTime::from_unix_time(123, 0)).unwrap();
        cache.watcher.discard_events();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert_eq!(cache.last_stats.tree_scans, 0);
        assert_eq!(cache.last_stats.canonical_reads, 0);
    }

    #[test]
    fn an_unwatched_directory_created_during_setup_is_not_admitted() {
        fn create_directory(key: &InputKey) {
            let InputKey::CompilerLibraryDirectory(root) = key else {
                unreachable!()
            };
            fs::create_dir_all(root.join("glibc-hwcaps/level")).unwrap();
        }
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let key = InputKey::CompilerLibraryDirectory(dir.path().to_owned());
        let mut cache = InputCache {
            before_tree_coverage: Some(create_directory),
            ..InputCache::default()
        };
        assert_eq!(
            evaluate(&mut cache, std::slice::from_ref(&key)),
            polled(std::slice::from_ref(&key))
        );
        assert!(!cache.topology.contains_key(&key));
        fs::write(dir.path().join("glibc-hwcaps/level/libnew.so.1"), "native").unwrap();
        assert_eq!(
            evaluate(&mut cache, std::slice::from_ref(&key)),
            polled(std::slice::from_ref(&key))
        );
        assert!(cache.last_stats.tree_scans > 0);
    }

    #[test]
    fn changes_after_a_cached_read_force_a_complete_poll() {
        fn create_file(key: &InputKey) {
            let InputKey::Directory(directory) = key else {
                unreachable!()
            };
            fs::write(directory.join("new"), "new").unwrap();
        }
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let keys = [InputKey::Directory(dir.path().to_owned())];
        let mut cache = InputCache::default();
        evaluate(&mut cache, &keys);
        cache.after_pass = Some(create_file);
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert_eq!(cache.last_stats.fallback_passes, 1);
    }

    #[test]
    fn overflow_and_backend_failure_preserve_polling_results() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let keys = [InputKey::Directory(dir.path().to_owned())];
        let mut cache = InputCache::default();
        evaluate(&mut cache, &keys);
        cache.simulate_overflow();
        fs::write(dir.path().join("after-overflow"), "new").unwrap();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert!(cache.last_stats.directory_reads > 0);
        cache.simulate_failure();
        fs::write(dir.path().join("after-failure"), "new").unwrap();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert!(cache.last_stats.directory_reads > 0);
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert!(cache.last_stats.directory_reads > 0);
    }

    #[test]
    fn structural_guards_detect_ancestor_replacement_without_notifications() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let ancestor = dir.path().join("ancestor");
        fs::create_dir_all(ancestor.join("libraries")).unwrap();
        let keys = [InputKey::CompilerLibraryDirectory(
            ancestor.join("libraries"),
        )];
        let mut cache = InputCache::default();
        evaluate(&mut cache, &keys);
        fs::rename(&ancestor, dir.path().join("old")).unwrap();
        fs::create_dir_all(ancestor.join("libraries")).unwrap();
        fs::write(ancestor.join("libraries/libnew.so"), "new").unwrap();
        cache.watcher.discard_events();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert!(cache.last_stats.tree_scans > 0);
    }

    #[test]
    fn canonical_guards_follow_intermediate_links_even_to_the_same_inode() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        fs::write(dir.path().join("a"), "same file").unwrap();
        fs::hard_link(dir.path().join("a"), dir.path().join("b")).unwrap();
        symlink("a", dir.path().join("middle")).unwrap();
        symlink("middle", dir.path().join("outer")).unwrap();
        let keys = [InputKey::Canonical(dir.path().join("outer"))];
        let mut cache = InputCache::default();
        let previous = evaluate(&mut cache, &keys);
        fs::remove_file(dir.path().join("middle")).unwrap();
        symlink("b", dir.path().join("middle")).unwrap();
        cache.watcher.discard_events();
        let current = evaluate(&mut cache, &keys);
        assert_eq!(current, polled(&keys));
        assert_ne!(current, previous);
        assert!(cache.last_stats.canonical_reads > 0);
    }

    #[test]
    fn canonical_guards_follow_links_before_trailing_dots_and_separators() {
        let Some(dir) = watched_tempdir() else {
            return;
        };
        fs::create_dir(dir.path().join("original")).unwrap();
        symlink("original", dir.path().join("link")).unwrap();
        let keys = [
            InputKey::Canonical(dir.path().join("link/")),
            InputKey::Canonical(dir.path().join("link/.")),
        ];
        let mut cache = InputCache::default();
        let previous = evaluate(&mut cache, &keys);
        assert_eq!(evaluate(&mut cache, &keys), previous);
        fs::rename(dir.path().join("original"), dir.path().join("moved")).unwrap();
        symlink("moved", dir.path().join("original")).unwrap();
        cache.watcher.discard_events();
        let current = evaluate(&mut cache, &keys);
        assert_eq!(current, polled(&keys));
        assert_ne!(current, previous);
    }

    #[test]
    fn exact_bytes_detect_mmap_writes_while_directory_topology_is_cached() {
        let Some(dir) = watched_tempdir() else {
            return; // This host uses the polling fallback.
        };
        let path = dir.path().join("Cargo.toml");
        fs::write(&path, "before").unwrap();
        let keys = [
            InputKey::Directory(dir.path().to_owned()),
            InputKey::File(path.clone()),
        ];
        let mut cache = InputCache::default();
        let previous = evaluate(&mut cache, &keys);
        let file = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .unwrap();
        // SAFETY: the file has six writable bytes, and the mapping is released
        // after the six-byte write before it is used again.
        unsafe {
            let mapping = libc::mmap(
                std::ptr::null_mut(),
                6,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_SHARED,
                file.as_raw_fd(),
                0,
            );
            assert_ne!(mapping, libc::MAP_FAILED);
            std::ptr::copy_nonoverlapping(b"after!".as_ptr(), mapping.cast::<u8>(), 6);
            assert_eq!(libc::munmap(mapping, 6), 0);
        }
        cache.watcher.discard_events();
        let current = evaluate(&mut cache, &keys);
        assert_eq!(current, polled(&keys));
        assert_ne!(current, previous);
        assert_eq!(cache.last_stats.directory_reads, 0);
    }

    #[test]
    fn overlapping_metadata_queries_share_only_the_current_pass() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("file");
        fs::write(&path, "file").unwrap();
        let keys = [
            InputKey::Exists(path.clone()),
            InputKey::IsFile(path.clone()),
            InputKey::IsDir(path.clone()),
        ];
        let mut cache = InputCache::default();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert_eq!(cache.last_stats.metadata_reads, 1);
        fs::remove_file(path).unwrap();
        assert_eq!(evaluate(&mut cache, &keys), polled(&keys));
        assert_eq!(cache.last_stats.metadata_reads, 1);
    }

    #[test]
    fn unsupported_filesystems_remain_polled() {
        let keys = [InputKey::Directory(PathBuf::from("/proc/self"))];
        let mut cache = InputCache::default();
        evaluate(&mut cache, &keys);
        evaluate(&mut cache, &keys);
        assert_eq!(cache.last_stats.directory_reads, 1);
        assert!(cache.topology.is_empty());
    }
}
