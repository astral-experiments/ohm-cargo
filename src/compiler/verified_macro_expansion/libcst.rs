use crate::compiler::{BuildRunner, CompileMode, CrateType, Unit, UnitHash};
use crate::util::data_structures::HashMap;
use crate::workspace::{Package, Target};

pub(in crate::compiler) fn target(package: &Package, target: &Target) -> bool {
    cfg!(unix)
        && target.name() == "libcst_native"
        && target.rustc_crate_types() == [CrateType::Cdylib, CrateType::Rlib]
        && package.package_id().source_id().is_crates_io()
        && package.name().as_str() == "libcst"
        && package.version() == &semver::Version::new(1, 9, 0)
        && package.summary().checksum()
            == Some("21b68d9c60cba9c333f89596ef5c4d3b6c9bd0b7d2e48a9810df6fa7976102a3")
}

pub(in crate::compiler) fn consumer(unit: &Unit) -> bool {
    unit.mode == CompileMode::Build && unit.features.is_empty() && target(&unit.pkg, &unit.target)
}

pub(in crate::compiler) fn paste_dependency(unit: &Unit) -> bool {
    unit.target.proc_macro()
        && unit.pkg.name().as_str() == "paste"
        && unit.pkg.version() == &semver::Version::new(1, 0, 15)
        && unit.pkg.summary().checksum()
            == Some("57c0d7b74b563b49d38dae00a0c37d4d6de9b432382b2892f0574ddcae73fd0a")
}

/// Rustc records every loaded crate, including proc macros which emitted no tokens.
/// The audited LibCST sources with Python disabled neither call nor re-export paste.
pub(in crate::compiler) fn verify(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    scripts: &HashMap<UnitHash, bool>,
) -> bool {
    #[cfg(unix)]
    {
        super::supported_invocation(runner, unit, scripts) && inspect(runner, unit).unwrap_or(false)
    }
    #[cfg(not(unix))]
    {
        let _ = (runner, unit, scripts);
        false
    }
}

#[cfg(unix)]
fn inspect(runner: &BuildRunner<'_, '_>, unit: &Unit) -> Option<bool> {
    use std::process::Stdio;
    let outputs = runner.outputs(unit).ok()?;
    let file = &outputs
        .iter()
        .find(|o| o.path.extension().is_some_and(|ext| ext == "rmeta"))?
        .path;
    let attributes = file.symlink_metadata().ok()?;
    if !attributes.is_file() || attributes.len() > 16 * 1024 * 1024 {
        return None;
    }
    let name = file.file_stem()?.to_str()?.strip_prefix("lib")?;
    let mut process = super::super::prepare_rustc(runner, unit).ok()?;
    let mut child = process
        .args_replace(&[std::ffi::OsStr::new("-Zls=root"), file.as_os_str()])
        .build_command()
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let dump = super::bounded_text(child.stdout.take()?, 64 * 1024);
    if !child.wait().ok()?.success() {
        return None;
    }
    Some(only_audited_macros(&dump?, name))
}

#[cfg(unix)]
fn only_audited_macros(dump: &str, name: &str) -> bool {
    let Some((header, deps)) = dump.split_once("\n=External Dependencies=\n") else {
        return false;
    };
    if !header.starts_with("Crate info:\n")
        || !header.lines().any(|line| line == "proc_macro false")
        || !header
            .lines()
            .nth(1)
            .is_some_and(|line| line.strip_prefix("name ") == Some(name))
    {
        return false;
    }
    let mut expected = [false; 3];
    for (index, line) in deps.trim_end().lines().enumerate() {
        let mut columns = line.split_ascii_whitespace();
        let [
            Some(id),
            Some(krate),
            Some("hash"),
            Some(hash),
            Some("host_hash"),
            Some("None"),
            Some("kind"),
            Some(kind),
            Some("public" | "private"),
            None,
        ] = std::array::from_fn(|_| columns.next())
        else {
            return false;
        };
        let krate = krate.split('-').next().unwrap_or("");
        if id.parse::<usize>() != Ok(index + 1)
            || hash.len() != 32
            || !hash.bytes().all(|ch| ch.is_ascii_hexdigit())
            || krate == "paste"
        {
            return false;
        }
        match kind {
            "Unconditional" | "Conditional" => {}
            "MacrosOnly" => {
                let Some(slot) = ["libcst_derive", "peg_macros", "thiserror_impl"]
                    .iter()
                    .position(|n| *n == krate)
                else {
                    return false;
                };
                if expected[slot] {
                    return false;
                }
                expected[slot] = true;
            }
            _ => return false,
        }
    }
    expected == [true; 3]
}

#[cfg(all(test, unix))]
mod tests {
    use super::only_audited_macros;

    #[test]
    fn rejects_loaded_paste_and_incomplete_native_metadata() {
        let mut root = String::from(
            "Crate info:\nname libcst_native-abcd\nproc_macro false\n=External Dependencies=\n",
        );
        let hash = "0123456789abcdef0123456789abcdef";
        for (index, name) in ["libcst_derive", "peg_macros", "thiserror_impl"]
            .iter()
            .enumerate()
        {
            root.push_str(&format!(
                "{} {name}-aa hash {hash} host_hash None kind MacrosOnly public\n",
                index + 1
            ));
        }
        assert!(only_audited_macros(&root, "libcst_native-abcd"));
        assert!(!only_audited_macros(&root, "other"));
        for invalid in [
            root.replace("peg_macros-aa", "paste-aa"),
            root.replace("peg_macros-aa", "another_macro"),
            root.replace("peg_macros-aa", "libcst_derive-ab"),
            root.replace("3 thiserror_impl-aa", "4 thiserror_impl-aa"),
            root.replace("host_hash None", "truncated"),
            root.lines().take(6).collect::<Vec<_>>().join("\n"),
        ] {
            assert!(!only_audited_macros(&invalid, "libcst_native-abcd"));
        }
    }
}
