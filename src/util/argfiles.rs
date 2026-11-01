//! Inputs passed to rustc and rustdoc through argument files.

use std::ffi::OsString;
use std::fs::OpenOptions;
use std::io::{Read, Write};

use cargo_util::ProcessBuilder;
use std::path::{Path, PathBuf};
use tempfile::NamedTempFile;

use crate::util::data_structures::HashMap;

/// Expands one level of argument files, following the compiler's line and shell formats.
pub(crate) fn expand<'a>(
    cwd: &Path,
    flags: impl Iterator<Item = &'a str>,
    sources: &mut HashMap<PathBuf, Option<String>>,
) -> Option<Vec<String>> {
    expand_with(cwd, flags, |_, path, shell, expanded| {
        let text = sources
            .entry(path.to_owned())
            .or_insert_with_key(|path| read_regular_file(path))
            .as_deref()?;
        append_file(text, shell, expanded)
    })
}

/// Expands a command while visiting its argument files in the driver's read order.
fn expand_with<'a>(
    cwd: &Path,
    flags: impl Iterator<Item = &'a str>,
    mut load: impl FnMut(&str, &Path, bool, &mut Vec<String>) -> Option<()>,
) -> Option<Vec<String>> {
    let mut expanded = Vec::new();
    let mut next_is_unstable = false;
    let mut shell_argfiles = false;
    for flag in flags {
        let start = expanded.len();
        if let Some(name) = flag.strip_prefix('@') {
            let shell_name = name.strip_prefix("shell:").filter(|_| shell_argfiles);
            load(
                flag,
                &cwd.join(shell_name.unwrap_or(name)),
                shell_name.is_some(),
                &mut expanded,
            )?;
        } else {
            expanded.push(flag.to_owned());
        }
        for arg in &expanded[start..] {
            if next_is_unstable {
                shell_argfiles |= arg == "shell-argfiles";
                next_is_unstable = false;
            } else if let Some(unstable) = arg.strip_prefix("-Z") {
                shell_argfiles |= unstable == "shell-argfiles";
                next_is_unstable = unstable.is_empty();
            }
        }
    }
    Some(expanded)
}

/// Appends arguments from a line-oriented or shell-quoted file.
fn append_file(text: &str, shell: bool, expanded: &mut Vec<String>) -> Option<()> {
    if shell {
        expanded.extend(shlex::split(text)?);
    } else {
        expanded.extend(text.lines().map(str::to_owned));
    }
    Some(())
}

/// Shares argument files between the crate build and the final HTML merge.
pub(crate) type SharedRustdocArgFiles = std::sync::Arc<std::sync::OnceLock<RustdocArgFiles>>;

/// Files captured during the unit build and reused by subsequent Rustdoc passes.
#[derive(Debug)]
pub(crate) struct RustdocArgFiles {
    copies: Vec<(String, OsString, NamedTempFile)>,
}

impl RustdocArgFiles {
    /// Replays only configured flags in the merge. They follow per-unit flags in the original command.
    pub(crate) fn configured_args(&self, flags: &[String]) -> Vec<OsString> {
        let mut copies = self.copies.iter().rev().peekable();
        let mut args: Vec<OsString> = flags.iter().map(OsString::from).collect();
        for arg in args.iter_mut().rev() {
            if let Some((raw, replacement, _)) = copies.peek()
                && arg == std::ffi::OsStr::new(raw)
            {
                *arg = replacement.clone();
                copies.next();
            }
        }
        args
    }
}

/// Snapshots inputs once when a Rustdoc command with untracked arguments must run twice.
pub(crate) fn snapshot_for_replay(cmd: &mut ProcessBuilder) -> crate::CargoResult<RustdocArgFiles> {
    let cwd = cmd.get_cwd().unwrap_or_else(|| Path::new("."));
    let mut copies = Vec::new();
    let mut snapshot_error = None;
    // Invalid or missing inputs must still reach Rustdoc for its own diagnostics.
    let _ = expand_with(
        cwd,
        cmd.get_args().map(|arg| arg.to_str().unwrap_or("")),
        |raw, path, shell, expanded| {
            let mut source = std::fs::File::open(path).ok()?;
            let mut bytes = Vec::new();
            if let Err(error) = source.read_to_end(&mut bytes) {
                snapshot_error = Some(anyhow::Error::new(error).context(format!(
                    "could not read Rustdoc argument file `{}`",
                    path.display()
                )));
                return None;
            }
            let copy = NamedTempFile::new().and_then(|mut file| {
                file.write_all(&bytes)?;
                Ok(file)
            });
            let file = match copy {
                Ok(file) => file,
                Err(error) => {
                    snapshot_error = Some(
                        anyhow::Error::new(error)
                            .context("could not save Rustdoc arguments for dependency collection"),
                    );
                    return None;
                }
            };
            let mut argument = OsString::from(if shell { "@shell:" } else { "@" });
            argument.push(file.path());
            copies.push((raw.to_owned(), argument, file));
            append_file(std::str::from_utf8(&bytes).ok()?, shell, expanded)
        },
    );
    if let Some(error) = snapshot_error {
        return Err(error);
    }
    for (raw, replacement, _) in &copies {
        anyhow::ensure!(
            cmd.replace_arg(raw, replacement),
            "could not replace Rustdoc argument {raw}"
        );
    }
    Ok(RustdocArgFiles { copies })
}

/// Leaves non-file inputs unread so the compiler can consume them exactly once.
fn read_regular_file(path: &Path) -> Option<String> {
    if !path.metadata().ok()?.is_file() {
        return None;
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NONBLOCK);
    }
    let mut file = options.open(path).ok()?;
    if !file.metadata().ok()?.is_file() {
        return None;
    }
    let mut contents = String::new();
    file.read_to_string(&mut contents).ok()?;
    Some(contents)
}
