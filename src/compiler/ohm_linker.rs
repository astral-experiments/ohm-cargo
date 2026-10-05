//! Bundled linker defaults. Keep these in unit rustflags so they affect fingerprints.

use std::path::Path;

use cargo_platform::{Cfg, CfgExpr};

use crate::util::{CargoResult, GlobalContext};
use crate::workspace::features::OhmLinker;

use super::CompileKind;

const TARGET: &str = "x86_64-unknown-linux-gnu";
pub(super) const FAST_COMPRESSION_FLAG: &str = "-Zartifact-compression-profile=fast";

/// Select storage independently from the linker used to consume its objects.
/// The v2 marker also promises rustc's ordinary-linker materialization adapter.
pub(super) fn flags(
    gctx: &GlobalContext,
    host: &str,
    kind: CompileKind,
    cfg: &[Cfg],
    sysroot: &Path,
    rustflags: &[String],
) -> CargoResult<Vec<String>> {
    let options = gctx.cli_unstable();
    let explicit_compact = options.ohm_compact_artifacts == Some(true);
    if host != TARGET
        || matches!(kind, CompileKind::Target(target) if target.rustc_target().as_str() != TARGET)
    {
        anyhow::ensure!(
            !explicit_compact,
            "-Zohm-compact-artifacts requires native x86_64-unknown-linux-gnu builds"
        );
        return Ok(Vec::new());
    }
    let capable = std::fs::read(wild_directory(sysroot).join("compact-artifacts-v2"))
        .is_ok_and(|bytes| bytes == b"RCOBJ001\n");
    anyhow::ensure!(
        !explicit_compact || capable,
        "-Zohm-compact-artifacts requires an Ohm compiler with compact-artifacts-v2 support"
    );
    let metadata_compatible =
        options.embed_metadata != Some(false) && options.no_embed_metadata != Some(true);
    if explicit_compact {
        anyhow::ensure!(
            metadata_compatible,
            "-Zohm-compact-artifacts requires embedded metadata"
        );
        validate_compact_flags(rustflags.iter().map(String::as_str))?;
    }
    let compact = options.ohm_compact_artifacts()
        && capable
        && metadata_compatible
        && validate_compact_flags(rustflags.iter().map(String::as_str)).is_ok();

    // Ordinary builds must leave linker configuration discovery to its existing callers.
    if !compact && options.ohm_linker() != Some(OhmLinker::Wild) {
        return Ok(Vec::new());
    }
    let use_host_config = kind.is_host() && !gctx.target_applies_to_host()?;
    let config = if use_host_config {
        gctx.host_cfg_triple(host)?
    } else {
        gctx.target_cfg_triple(TARGET)?
    };
    let explicit_linker = has_linker_overrides(rustflags.iter().map(String::as_str), true)
        || config.linker.is_some()
        || (!use_host_config
            && gctx
                .target_cfgs()?
                .iter()
                .any(|(key, config)| config.linker.is_some() && CfgExpr::matches_key(key, cfg)));
    let wild = options.ohm_linker() == Some(OhmLinker::Wild)
        && !explicit_linker
        && (options.ohm_linker.is_some() || wild_directory(sysroot).join("ld.bfd").is_file());
    let mut flags = if wild {
        vec![
            "-Clinker-features=-lld".into(),
            "-Clink-self-contained=-linker".into(),
            format!("-Clink-arg=-B{}", wild_directory(sysroot).display()),
            // Older GCC releases do not recognize -fuse-ld=wild. Both GCC and
            // Clang resolve this private ld.bfd through the preceding -B path.
            "-Clink-arg=-fuse-ld=bfd".into(),
        ]
    } else {
        Vec::new()
    };
    if compact {
        if wild {
            flags.push(COMPACT_LINKER_FLAG.into());
        }
        flags.push(COMPACT_FLAG.into());
        if !has_compression_options(rustflags.iter().map(String::as_str)) {
            flags.push(FAST_COMPRESSION_FLAG.into());
        }
    }
    Ok(flags)
}

pub(super) const COMPACT_FLAG: &str = "-Zcompact-artifacts=yes";
pub(super) const COMPACT_LINKER_FLAG: &str = "-Zcompact-artifacts-linker=yes";

/// The generated Wild driver flags precede storage flags in the authenticated suffix.
pub(super) fn wild_flag_count(flags: &[String]) -> usize {
    if flags
        .first()
        .is_some_and(|flag| flag == "-Clinker-features=-lld")
    {
        4 + usize::from(flags.get(4).is_some_and(|flag| flag == COMPACT_LINKER_FLAG))
    } else {
        0
    }
}

pub(super) fn wild_directory(sysroot: &Path) -> std::path::PathBuf {
    sysroot.join("lib/rustlib").join(TARGET).join("bin/wild-ld")
}

/// User metadata/format choices take precedence over automatic compact storage.
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
        // Rustc expands these before parsing, including a response used as an option value.
        if let Some(response) = std::iter::once(arg)
            .chain(option)
            .find(|arg| arg.starts_with('@'))
        {
            anyhow::bail!(
                "-Zohm-compact-artifacts cannot be combined with opaque rustc response file `{response}`"
            );
        }
        let Some(option) = option else { continue };
        let (name, value) = option.split_once('=').unwrap_or((option, ""));
        let incompatible = match name.replace('_', "-").as_str() {
            "compact-artifacts" | "compact-artifacts-linker" => true,
            "embed-metadata" => matches!(value, "n" | "no" | "off" | "false"),
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

/// Preserve user linker selection and let rustc materialize objects for ordinary linkers.
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
            name if name.starts_with('@') => return true,
            "linker-plugin-lto" if !matches!(value, "n" | "no" | "off" | "false") => {
                // Wild does not provide the LLVM linker plugin. Retain the platform/user linker.
                return true;
            }
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
        for defaults in [false, true] {
            for selection in [None, Some(false), Some(true)] {
                let options = CliUnstable {
                    ohm_defaults: Some(defaults),
                    ohm_compact_artifacts: selection,
                    ..CliUnstable::default()
                };
                assert_eq!(
                    options.ohm_compact_artifacts(),
                    selection.unwrap_or(defaults)
                );
            }
        }
        let compact = CliUnstable {
            ohm_defaults: Some(false),
            ohm_compact_artifacts: Some(true),
            ..CliUnstable::default()
        };
        assert_eq!(compact.ohm_linker(), Some(OhmLinker::Wild));
        assert_eq!(CliUnstable::default().ohm_compact_artifacts, None);
    }

    #[test]
    fn compact_capability_fallback_and_independent_linker_selection() {
        use crate::Shell;
        use crate::compiler::{CompileKind, CompileTarget};
        use crate::util::GlobalContext;
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path();
        let directory = super::wild_directory(root);
        std::fs::create_dir_all(&directory).unwrap();
        std::fs::write(directory.join("ld.bfd"), b"fixture").unwrap();
        let select = |options: &[&str], args: &[&str], host: &str, kind, config: &[&str]| {
            let mut gctx = GlobalContext::new(Shell::new(), root.into(), root.join("home"));
            gctx.nightly_features_allowed = true;
            gctx.set_env(Default::default());
            gctx.set_search_stop_path(root);
            gctx.configure(
                0,
                false,
                None,
                false,
                false,
                false,
                &None,
                &options.iter().map(|s| (*s).into()).collect::<Vec<_>>(),
                &config.iter().map(|s| (*s).into()).collect::<Vec<_>>(),
            )
            .unwrap();
            super::flags(
                &gctx,
                host,
                kind,
                &[],
                root,
                &args.iter().map(|s| (*s).into()).collect::<Vec<_>>(),
            )
        };
        let auto = ["ohm-defaults=yes"];
        let yes = ["ohm-defaults=no", "ohm-compact-artifacts=yes"];
        let has = |flags: &[String], flag: &str| flags.iter().any(|s| s == flag);
        for old_marker in [false, true] {
            if old_marker {
                std::fs::write(directory.join("compact-artifacts-v1"), b"RCOBJ001\n").unwrap();
            }
            let flags = select(&auto, &[], super::TARGET, CompileKind::Host, &[]).unwrap();
            assert!(!has(&flags, super::COMPACT_FLAG));
            assert!(!has(&flags, super::COMPACT_LINKER_FLAG));
            assert!(select(&yes, &[], super::TARGET, CompileKind::Host, &[]).is_err());
        }
        std::fs::write(directory.join("compact-artifacts-v2"), b"wrong").unwrap();
        assert!(!has(
            &select(&auto, &[], super::TARGET, CompileKind::Host, &[]).unwrap(),
            super::COMPACT_FLAG
        ));
        std::fs::write(directory.join("compact-artifacts-v2"), b"RCOBJ001\n").unwrap();
        for response in [
            vec!["@user-rustflags"],
            vec!["-Z", "@unstable-options"],
            vec!["-C", "@codegen-options"],
            vec!["--codegen", "@codegen-options"],
        ] {
            assert!(
                select(&auto, &response, super::TARGET, CompileKind::Host, &[])
                    .unwrap()
                    .is_empty(),
                "{response:?}"
            );
            assert!(
                select(&yes, &response, super::TARGET, CompileKind::Host, &[])
                    .unwrap_err()
                    .to_string()
                    .contains("opaque rustc response file")
            );
        }
        for options in [&auto[..], &yes[..]] {
            let flags = select(options, &[], super::TARGET, CompileKind::Host, &[]).unwrap();
            assert!(has(&flags, super::COMPACT_FLAG));
            assert!(has(&flags, super::COMPACT_LINKER_FLAG));
            assert_eq!(super::wild_flag_count(&flags), 5);
            for args in [
                vec!["-Clinker=clang"],
                vec!["-Clink-arg=-fuse-ld=lld"],
                vec!["-Clinker-plugin-lto"],
            ] {
                let flags = select(options, &args, super::TARGET, CompileKind::Host, &[]).unwrap();
                assert!(has(&flags, super::COMPACT_FLAG));
                assert!(!has(&flags, super::COMPACT_LINKER_FLAG));
                assert_eq!(super::wild_flag_count(&flags), 0);
            }
            for args in [
                vec!["-Clto=thin"],
                vec!["-Csplit-debuginfo=packed"],
                vec!["-Clink-arg=-pthread"],
            ] {
                let flags = select(options, &args, super::TARGET, CompileKind::Host, &[]).unwrap();
                assert!(has(&flags, super::COMPACT_FLAG));
                assert!(has(&flags, super::COMPACT_LINKER_FLAG));
            }
            let flags = select(
                options,
                &[],
                super::TARGET,
                CompileKind::Host,
                &["target.x86_64-unknown-linux-gnu.linker='clang'"],
            )
            .unwrap();
            assert!(has(&flags, super::COMPACT_FLAG));
            assert!(!has(&flags, super::COMPACT_LINKER_FLAG));
        }
        for option in ["ohm-compact-artifacts=no", "embed-metadata=no"] {
            let flags = select(
                &["ohm-defaults=yes", option],
                &[],
                super::TARGET,
                CompileKind::Host,
                &[],
            )
            .unwrap();
            assert!(!has(&flags, super::COMPACT_FLAG));
            assert!(!has(&flags, super::COMPACT_LINKER_FLAG));
        }
        for value in ["n", "no", "off", "false"] {
            let flag = format!("-Zembed-metadata={value}");
            let flags = select(&auto, &[&flag], super::TARGET, CompileKind::Host, &[]).unwrap();
            assert!(!has(&flags, super::COMPACT_FLAG), "{value}");
            assert!(select(&yes, &[&flag], super::TARGET, CompileKind::Host, &[]).is_err());
            assert!(!has_linker_overrides(
                [format!("-Clinker-plugin-lto={value}").as_str()],
                true
            ));
        }
        let flags = select(
            &["ohm-defaults=yes", "ohm-linker=lld"],
            &[],
            super::TARGET,
            CompileKind::Host,
            &[],
        )
        .unwrap();
        assert!(has(&flags, super::COMPACT_FLAG));
        assert!(!has(&flags, super::COMPACT_LINKER_FLAG));
        let cross =
            CompileKind::Target(CompileTarget::new("aarch64-unknown-linux-gnu", false).unwrap());
        for (host, kind) in [
            ("aarch64-apple-darwin", CompileKind::Host),
            (super::TARGET, cross),
        ] {
            assert!(select(&auto, &[], host, kind, &[]).unwrap().is_empty());
            assert!(select(&yes, &[], host, kind, &[]).is_err());
        }
    }

    #[test]
    fn compact_option_compatibility() {
        for args in [
            vec!["-Zcompact-artifacts=no"],
            vec!["-Zembed-metadata=no"],
            vec!["@user-rustflags"],
            vec!["-Z", "@unstable-options"],
        ] {
            assert!(validate_compact_flags(args.clone()).is_err(), "{args:?}");
        }
        for args in [
            vec!["-C", "lto=thin"],
            vec!["--codegen=lto"],
            vec!["-Clinker_plugin_lto=yes"],
            vec!["--codegen", "split-debuginfo=packed"],
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
            vec!["-Z", "@flags"],
            vec!["-C", "@flags"],
            vec!["--codegen", "@flags"],
        ] {
            assert!(has_linker_overrides(args, false));
        }
        assert!(!has_linker_overrides(
            ["-Cdebuginfo=1", "--cfg", "test"],
            false
        ));
    }
}
