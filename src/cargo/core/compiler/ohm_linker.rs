//! Bundled linker defaults. Keep these in unit rustflags so they affect fingerprints.

use std::path::Path;

use cargo_platform::{Cfg, CfgExpr};

use crate::core::features::OhmLinker;
use crate::util::{CargoResult, GlobalContext};

use super::CompileKind;

const TARGET: &str = "x86_64-unknown-linux-gnu";

/// Return driver flags only when no applicable user linker configuration exists.
pub(super) fn flags(
    gctx: &GlobalContext,
    host: &str,
    kind: CompileKind,
    cfg: &[Cfg],
    sysroot: &Path,
    rustflags: &[String],
) -> CargoResult<Vec<String>> {
    let Some(linker) = gctx.cli_unstable().ohm_linker() else {
        return Ok(Vec::new());
    };
    if host != TARGET
        || matches!(kind, CompileKind::Target(target) if target.rustc_target().as_str() != TARGET)
        || has_linker_flags(rustflags.iter().map(String::as_str))
    {
        return Ok(Vec::new());
    }
    // A standalone Ohm Cargo can also drive an older compiler without Wild.
    // Only automatic selection falls back; explicit Wild requests still fail
    // in prepare_rustc when the bundled executable is missing.
    if linker == OhmLinker::Wild
        && gctx.cli_unstable().ohm_linker.is_none()
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
        return Ok(Vec::new());
    }

    Ok(match linker {
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
    })
}

pub(super) fn wild_directory(sysroot: &Path) -> std::path::PathBuf {
    sysroot.join("lib/rustlib").join(TARGET).join("bin/wild-ld")
}

/// Treat opaque response files and driver arguments as explicit linker choices.
pub(super) fn has_linker_flags<'a>(args: impl IntoIterator<Item = &'a str>) -> bool {
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if arg.starts_with('@') {
            return true;
        }
        let option = if arg == "-C" || arg == "--codegen" {
            args.next()
        } else {
            arg.strip_prefix("-C")
                .or_else(|| arg.strip_prefix("--codegen="))
        };
        if option.is_some_and(|option| {
            matches!(
                option.split('=').next().unwrap().replace('_', "-").as_str(),
                "linker"
                    | "linker-flavor"
                    | "linker-features"
                    | "link-self-contained"
                    | "link-arg"
                    | "link-args"
            )
        }) {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::has_linker_flags;
    use crate::core::features::{CliUnstable, OhmLinker};

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
            assert!(has_linker_flags(args));
        }
        assert!(!has_linker_flags(["-Cdebuginfo=1", "--cfg", "test"]));
    }
}
