//! Immutable, invocation-pinned generations of pure registry library artifacts.
//!
//! Compiler outputs never move: rustc and pipelined consumers use the eventual generation
//! directory from the start. Only the small `current` pointer changes, after the complete
//! build succeeds. Failed builds drop their unpublished directories, leaving readers alone.

use std::fs;
use std::io::{Read as _, Write as _};
use std::path::{Path, PathBuf};

use cargo_util::paths;

use crate::CargoResult;

/// Explicit output overrides bypass the generation directory selected by Cargo.
pub(super) fn has_custom_output_paths<'a>(arguments: impl IntoIterator<Item = &'a str>) -> bool {
    let mut arguments = arguments.into_iter();
    while let Some(argument) = arguments.next() {
        if argument.starts_with("-o")
            || matches!(
                argument.split('=').next(),
                Some("--out-dir" | "--emit" | "--crate-type" | "--test")
            )
        {
            return true;
        }
        let option = if matches!(argument, "-C" | "-Z" | "--codegen") {
            let Some(option) = arguments.next() else {
                return true;
            };
            Some(option)
        } else {
            argument
                .strip_prefix("-C")
                .or_else(|| argument.strip_prefix("-Z"))
                .or_else(|| argument.strip_prefix("--codegen="))
        };
        if option.is_some_and(|option| {
            matches!(
                option.split('=').next(),
                Some("incremental" | "temps-dir" | "temps_dir" | "no-link" | "no_link")
            )
        }) {
            return true;
        }
    }
    false
}

pub(super) struct RegistryGeneration {
    root: PathBuf,
    directory: PathBuf,
    unpublished: Option<tempfile::TempDir>,
    needs_publication: bool,
}

impl RegistryGeneration {
    pub(super) fn open(root: PathBuf) -> CargoResult<Self> {
        if let Some(directory) = Self::current(&root) {
            return Ok(Self {
                root,
                directory,
                unpublished: None,
                needs_publication: false,
            });
        }
        Self::new(root)
    }

    fn current(root: &Path) -> Option<PathBuf> {
        let generations = root.join("generations");
        if !fs::symlink_metadata(&generations).ok()?.is_dir() {
            return None;
        }
        let pointer = root.join("current");
        if !fs::symlink_metadata(&pointer).ok()?.is_file() {
            return None;
        }
        let mut name = String::new();
        fs::File::open(pointer)
            .ok()?
            .take(129)
            .read_to_string(&mut name)
            .ok()?;
        // The pointer is an identifier, never an arbitrary path. In particular, do not
        // follow symlinks or allow a corrupted pointer to escape this unit's namespace.
        if name.len() > 128
            || !name.starts_with("generation-")
            || !name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
        {
            return None;
        }
        let directory = generations.join(name);
        fs::symlink_metadata(&directory)
            .ok()?
            .is_dir()
            .then_some(directory)
    }

    fn new(root: PathBuf) -> CargoResult<Self> {
        let generations = root.join("generations");
        paths::create_dir_all(&generations)?;
        if !fs::symlink_metadata(&generations)?.is_dir() {
            anyhow::bail!(
                "immutable registry generations require a real directory at {}",
                generations.display()
            );
        }
        let unpublished = tempfile::Builder::new()
            .prefix("generation-")
            .tempdir_in(generations)?;
        Ok(Self {
            directory: unpublished.path().to_path_buf(),
            root,
            unpublished: Some(unpublished),
            needs_publication: true,
        })
    }

    pub(super) fn replace(&mut self) -> CargoResult<()> {
        *self = Self::new(self.root.clone())?;
        Ok(())
    }

    pub(super) fn name(&self) -> &str {
        self.directory.file_name().unwrap().to_str().unwrap()
    }

    pub(super) fn is_published(&self) -> bool {
        !self.needs_publication
    }

    /// Keep all completed directories before advertising any of them. A failed pointer
    /// update must not drop a dependency of a generation already visible to another Cargo.
    pub(super) fn retain(&mut self) {
        if let Some(directory) = self.unpublished.take() {
            let _ = directory.keep();
        }
    }

    pub(super) fn publish(&mut self) -> CargoResult<()> {
        if self.needs_publication {
            assert!(self.unpublished.is_none());
            // Unlike paths::write_atomic, replacing the pointer must not follow a symlink.
            let mut pointer = tempfile::Builder::new()
                .prefix(".current-")
                .tempfile_in(&self.root)?;
            pointer.write_all(self.name().as_bytes())?;
            pointer.persist(self.root.join("current"))?;
            self.needs_publication = false;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn custom_output_paths_are_not_generation_safe() {
        for flags in [
            vec!["--out-dir=elsewhere"],
            vec!["--emit", "metadata=elsewhere"],
            vec!["-oelsewhere"],
            vec!["--crate-type=dylib"],
            vec!["-C", "incremental=elsewhere"],
            vec!["-Cincremental=elsewhere"],
            vec!["--codegen=incremental=elsewhere"],
            vec!["-Ztemps-dir=elsewhere"],
            vec!["-Z", "no-link"],
        ] {
            assert!(has_custom_output_paths(flags));
        }
        assert!(!has_custom_output_paths([
            "-C",
            "opt-level=3",
            "-Zcache-proc-macros"
        ]));
    }

    #[test]
    fn publication_keeps_existing_readers_and_discards_failed_writers() {
        let root = tempfile::tempdir().unwrap();
        let mut first = RegistryGeneration::open(root.path().to_path_buf()).unwrap();
        fs::write(first.directory.join("artifact"), b"first").unwrap();
        assert!(!root.path().join("current").exists());
        first.retain();
        first.publish().unwrap();
        let reader = RegistryGeneration::open(root.path().to_path_buf()).unwrap();

        let abandoned;
        {
            let mut writer = RegistryGeneration::open(root.path().to_path_buf()).unwrap();
            writer.replace().unwrap();
            abandoned = writer.directory.clone();
            fs::write(abandoned.join("artifact"), b"incomplete").unwrap();
            assert_eq!(
                RegistryGeneration::current(root.path()),
                Some(reader.directory.clone())
            );
        }
        assert!(!abandoned.exists());

        let mut writer = RegistryGeneration::open(root.path().to_path_buf()).unwrap();
        writer.replace().unwrap();
        fs::write(writer.directory.join("artifact"), b"second").unwrap();
        writer.retain();
        writer.publish().unwrap();
        assert_eq!(
            RegistryGeneration::current(root.path()),
            Some(writer.directory.clone())
        );
        assert_eq!(
            fs::read(reader.directory.join("artifact")).unwrap(),
            b"first"
        );
    }

    #[test]
    fn malformed_generation_pointers_are_cache_misses() {
        let root = tempfile::tempdir().unwrap();
        for name in [
            "../outside",
            "generation-missing",
            "generation-../outside",
            "",
        ] {
            fs::write(root.path().join("current"), name).unwrap();
            let generation = RegistryGeneration::open(root.path().to_path_buf()).unwrap();
            assert!(!generation.is_published());
            assert!(
                generation
                    .directory
                    .starts_with(root.path().join("generations"))
            );
            assert_eq!(
                fs::read_to_string(root.path().join("current")).unwrap(),
                name
            );
        }
    }

    #[cfg(unix)]
    #[test]
    fn publication_replaces_a_pointer_symlink_without_following_it() {
        let root = tempfile::tempdir().unwrap();
        let outside = root.path().join("outside");
        fs::write(&outside, b"untouched").unwrap();
        std::os::unix::fs::symlink(&outside, root.path().join("current")).unwrap();
        let mut generation = RegistryGeneration::open(root.path().to_path_buf()).unwrap();
        generation.retain();
        generation.publish().unwrap();
        assert_eq!(fs::read(outside).unwrap(), b"untouched");
        assert!(!root.path().join("current").is_symlink());
        assert_eq!(
            RegistryGeneration::current(root.path()),
            Some(generation.directory)
        );
    }

    #[cfg(unix)]
    #[test]
    fn staging_rejects_a_symlinked_generations_directory() {
        let root = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        std::os::unix::fs::symlink(outside.path(), root.path().join("generations")).unwrap();
        assert!(RegistryGeneration::open(root.path().to_path_buf()).is_err());
        assert_eq!(fs::read_dir(outside.path()).unwrap().count(), 0);
    }
}
