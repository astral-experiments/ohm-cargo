//! Inputs passed to rustc and rustdoc through argument files.

use std::fs::OpenOptions;
use std::io::Read;
use std::path::{Path, PathBuf};

use crate::util::data_structures::HashMap;

/// Expands one level of argument files, following the compiler's line and shell formats.
pub(crate) fn expand<'a>(
    cwd: &Path,
    flags: impl Iterator<Item = &'a str>,
    sources: &mut HashMap<PathBuf, Option<String>>,
) -> Option<Vec<String>> {
    let mut expanded = Vec::new();
    let mut next_is_unstable = false;
    let mut shell_argfiles = false;
    for flag in flags {
        let start = expanded.len();
        if let Some(name) = flag.strip_prefix('@') {
            let shell_name = name.strip_prefix("shell:").filter(|_| shell_argfiles);
            let text = sources
                .entry(cwd.join(shell_name.unwrap_or(name)))
                .or_insert_with_key(|path| read_regular_file(path))
                .as_deref()?;
            if shell_name.is_some() {
                expanded.extend(shlex::split(text)?);
            } else {
                expanded.extend(text.lines().map(str::to_owned));
            }
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
