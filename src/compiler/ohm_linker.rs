//! Bundled linker defaults. Keep these in unit rustflags so they affect fingerprints.

use std::path::Path;

use cargo_platform::{Cfg, CfgExpr};

use crate::util::{CargoResult, GlobalContext};
use crate::workspace::features::OhmLinker;

use super::CompileKind;

const TARGET: &str = "x86_64-unknown-linux-gnu";
pub(super) const FAST_COMPRESSION_FLAG: &str = "-Zartifact-compression-profile=fast";

/// Return driver flags only when no applicable user linker configuration exists.
pub(super) fn flags(
    gctx: &GlobalContext,
    host: &str,
    kind: CompileKind,
    cfg: &[Cfg],
    sysroot: &Path,
    rustflags: &[String],
) -> CargoResult<Vec<String>> {
    let compact = gctx.cli_unstable().ohm_compact_artifacts;
    let Some(linker) = gctx.cli_unstable().ohm_linker() else {
        return Ok(Vec::new());
    };
    anyhow::ensure!(
        !compact || linker == OhmLinker::Wild,
        "-Zohm-compact-artifacts requires the bundled Wild linker, not -Zohm-linker=lld"
    );
    if host != TARGET
        || matches!(kind, CompileKind::Target(target) if target.rustc_target().as_str() != TARGET)
    {
        anyhow::ensure!(
            !compact,
            "-Zohm-compact-artifacts requires native x86_64-unknown-linux-gnu builds"
        );
        return Ok(Vec::new());
    }
    if has_linker_overrides(rustflags.iter().map(String::as_str), compact) {
        anyhow::ensure!(
            !compact,
            "-Zohm-compact-artifacts cannot be combined with explicit linker flags"
        );
        return Ok(Vec::new());
    }
    if compact {
        validate_compact_flags(rustflags.iter().map(String::as_str))?;
        anyhow::ensure!(
            gctx.cli_unstable().embed_metadata != Some(false)
                && gctx.cli_unstable().no_embed_metadata != Some(true),
            "-Zohm-compact-artifacts requires embedded metadata"
        );
        anyhow::ensure!(
            wild_directory(sysroot).join("ld.bfd").is_file()
                && std::fs::read(wild_directory(sysroot).join("compact-artifacts-v1"))
                    .is_ok_and(|bytes| bytes == b"RCOBJ001\n"),
            "-Zohm-compact-artifacts requires an Ohm toolchain with compact-capable bundled Wild"
        );
    }
    // A standalone Ohm Cargo can also drive an older compiler without Wild.
    // Only automatic selection falls back; explicit Wild requests still fail
    // in prepare_rustc when the bundled executable is missing.
    if linker == OhmLinker::Wild
        && gctx.cli_unstable().ohm_linker.is_none()
        && !compact
        && !wild_directory(sysroot).join("ld.bfd").is_file()
    {
        return Ok(Vec::new());
    }

    let use_host_config = kind.is_host() && !gctx.target_applies_to_host()?;
    let config = if use_host_config {
        gctx.host_cfg_triple(host)?
    } else {
        gctx.target_cfg_triple(TARGET)?
    };
    if config.linker.is_some()
        || (!use_host_config
            && gctx
                .target_cfgs()?
                .iter()
                .any(|(key, config)| config.linker.is_some() && CfgExpr::matches_key(key, cfg)))
    {
        anyhow::ensure!(
            !compact,
            "-Zohm-compact-artifacts cannot be combined with explicit linker configuration"
        );
        return Ok(Vec::new());
    }

    let mut flags = match linker {
        OhmLinker::Wild => vec![
            "-Clinker-features=-lld".into(),
            "-Clink-self-contained=-linker".into(),
            format!("-Clink-arg=-B{}", wild_directory(sysroot).display()),
            // Older GCC releases do not recognize -fuse-ld=wild. Both GCC and
            // Clang resolve this private ld.bfd through the preceding -B path.
            "-Clink-arg=-fuse-ld=bfd".into(),
        ],
        // Restore the native GNU target's bundled LLD default. Explicit +lld
        // flags need -Zunstable-options; the target default needs neither.
        OhmLinker::Lld => Vec::new(),
    };
    if compact {
        flags.push("-Zcompact-artifacts=yes".into());
        if !has_compression_options(rustflags.iter().map(String::as_str)) {
            flags.push(FAST_COMPRESSION_FLAG.into());
        }
    }
    Ok(flags)
}

pub(super) fn wild_directory(sysroot: &Path) -> std::path::PathBuf {
    sysroot.join("lib/rustlib").join(TARGET).join("bin/wild-ld")
}

/// Reject format and code-generation overrides that cannot use the compact-object lane.
pub(super) fn validate_compact_flags<'a>(
    args: impl IntoIterator<Item = &'a str>,
) -> CargoResult<()> {
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        let option = if matches!(arg, "-C" | "--codegen" | "-Z") {
            args.next()
        } else {
            arg.strip_prefix("-C")
                .or_else(|| arg.strip_prefix("--codegen="))
                .or_else(|| arg.strip_prefix("-Z"))
        };
        let Some(option) = option else { continue };
        let (name, value) = option.split_once('=').unwrap_or((option, ""));
        let incompatible = match name.replace('_', "-").as_str() {
            "lto" | "linker-plugin-lto" => !matches!(value, "off" | "no" | "false"),
            "split-debuginfo" => value == "packed",
            "compact-artifacts" => true,
            "embed-metadata" => matches!(value, "no" | "false"),
            _ => false,
        };
        anyhow::ensure!(
            !incompatible,
            "-Zohm-compact-artifacts cannot be combined with `{option}`"
        );
    }
    Ok(())
}

/// Preserve explicit codec tuning instead of appending a later default over it.
pub(super) fn has_compression_options<'a>(args: impl IntoIterator<Item = &'a str>) -> bool {
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        let option = if arg == "-Z" {
            args.next()
        } else {
            arg.strip_prefix("-Z")
        };
        if option.is_some_and(|option| {
            matches!(
                option.split('=').next().unwrap().replace('_', "-").as_str(),
                "artifact-compression-profile"
                    | "artifact-compression-level"
                    | "artifact-compression-chunk-size"
            )
        }) {
            return true;
        }
    }
    false
}

/// Build-script linker arguments arrive after the bundled linker flags have been selected.
fn selects_linker(arg: &str) -> bool {
    [
        "@",
        "-B",
        "-fuse-ld",
        "--ld-path",
        "-specs",
        "--specs",
        "-wrapper",
        "--gcc-toolchain",
        "-gcc-toolchain",
        "--sysroot",
        "-isysroot",
    ]
    .iter()
    .any(|prefix| arg.starts_with(prefix))
}

/// Compact mode requires Wild but accepts native arguments that preserve its selection.
pub(super) fn has_linker_overrides<'a>(
    args: impl IntoIterator<Item = &'a str>,
    allow_native_args: bool,
) -> bool {
    let mut driver_args = Vec::new();
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if arg.starts_with('@') {
            return true;
        }
        let option = if matches!(arg, "-C" | "--codegen" | "-Z") {
            args.next()
        } else {
            arg.strip_prefix("-C")
                .or_else(|| arg.strip_prefix("--codegen="))
                .or_else(|| arg.strip_prefix("-Z"))
        };
        let Some(option) = option else { continue };
        let (name, value) = option.split_once('=').unwrap_or((option, ""));
        match name.replace('_', "-").as_str() {
            "linker" | "linker-flavor" | "linker-features" | "link-self-contained" => {
                return true;
            }
            "link-arg" | "pre-link-arg" => {
                if !allow_native_args {
                    return true;
                }
                driver_args.push(value);
            }
            "link-args" | "pre-link-args" => {
                if !allow_native_args {
                    return true;
                }
                driver_args.extend(value.split_whitespace());
            }
            _ => {}
        }
    }
    linker_selection(driver_args).is_some()
}

/// Locate a driver override while respecting arguments forwarded directly to the linker.
pub(super) fn linker_selection<'a>(args: impl IntoIterator<Item = &'a str>) -> Option<&'a str> {
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if arg == "-Xlinker" {
            // The next argument is forwarded to Wild, not interpreted by the C driver.
            args.next();
        } else if selects_linker(arg) {
            return Some(arg);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::{
        has_compression_options, has_linker_overrides, selects_linker, validate_compact_flags,
    };
    use crate::workspace::features::{CliUnstable, OhmLinker};

    #[test]
    fn defaults_and_explicit_linker_selection() {
        for defaults in [false, true] {
            for selection in [None, Some(OhmLinker::Wild), Some(OhmLinker::Lld)] {
                let options = CliUnstable {
                    ohm_defaults: Some(defaults),
                    ohm_linker: selection,
                    ..CliUnstable::default()
                };
                assert_eq!(
                    options.ohm_linker(),
                    selection.or(defaults.then_some(OhmLinker::Wild))
                );
            }
        }
        assert_eq!(
            CliUnstable::default().ohm_linker(),
            cfg!(feature = "ohm-defaults").then_some(OhmLinker::Wild)
        );
        let compact = CliUnstable {
            ohm_defaults: Some(false),
            ohm_compact_artifacts: true,
            ..CliUnstable::default()
        };
        assert_eq!(compact.ohm_linker(), Some(OhmLinker::Wild));
        assert!(!CliUnstable::default().ohm_compact_artifacts);
    }

    #[test]
    fn compact_option_compatibility() {
        for args in [
            vec!["-C", "lto=thin"],
            vec!["--codegen=lto"],
            vec!["-Clinker_plugin_lto=yes"],
            vec!["--codegen", "split-debuginfo=packed"],
            vec!["-Zcompact-artifacts=no"],
            vec!["-Zembed-metadata=no"],
        ] {
            assert!(validate_compact_flags(args.clone()).is_err(), "{args:?}");
        }
        for args in [
            vec!["-Clto=off", "-Clinker-plugin-lto=no"],
            vec!["-Csplit-debuginfo=unpacked", "--cfg", "test"],
            vec!["-Z", "artifact_compression_level=2"],
            vec!["-Zartifact-compression-profile=small"],
        ] {
            assert!(validate_compact_flags(args.clone()).is_ok(), "{args:?}");
        }
        assert!(has_compression_options([
            "-Z",
            "artifact_compression_level=2"
        ]));
        assert!(has_compression_options([
            "-Zartifact-compression-profile=small"
        ]));
        assert!(!has_compression_options([
            "-Zpublic-api-hash",
            "-Cdebuginfo=1"
        ]));
        for arg in [
            "-fuse-ld=lld",
            "-B/other",
            "--ld-path=custom",
            "@driver.rsp",
            "-specs=custom",
        ] {
            assert!(selects_linker(arg), "{arg}");
        }
        assert!(!has_linker_overrides(
            [
                "-Clink-arg=-Wl,-rpath,/native/lib",
                "-Clink-args=-Xlinker -Bsymbolic -pthread"
            ],
            true
        ));
        for flag in [
            "-Clink-arg=-fuse-ld=lld",
            "-Zpre-link-args=-B/other",
            "-Clink-args=-pthread @driver.rsp",
        ] {
            assert!(has_linker_overrides([flag], true), "{flag}");
        }
        for arg in ["-Wl,-rpath,/native/lib", "-Wl,--no-as-needed", "-pthread"] {
            assert!(!selects_linker(arg), "{arg}");
        }
    }

    #[test]
    fn explicit_linker_controls() {
        for args in [
            vec!["-Clinker=clang"],
            vec!["-C", "linker=clang"],
            vec!["--codegen", "link_arg=-fuse-ld=mold"],
            vec!["--codegen=linker-flavor=gnu-lld-cc"],
            vec!["-Clink-self-contained=+linker"],
            vec!["-Clinker-features=-lld"],
            vec!["@flags"],
        ] {
            assert!(has_linker_overrides(args, false));
        }
        assert!(!has_linker_overrides(
            ["-Cdebuginfo=1", "--cfg", "test"],
            false
        ));
    }
}
