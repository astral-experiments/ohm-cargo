#[cfg(unix)]
mod cache;
#[cfg(unix)]
use std::str::FromStr;

#[cfg(unix)]
use proc_macro2::{TokenStream, TokenTree};

use super::{BuildRunner, CompileMode, Unit, UnitHash};
use crate::util::data_structures::HashMap;

const DISPLAYDOC_CHECKSUM: &str =
    "97369cbbc041bc366949bc74d34658d6cda5621039731c6310521892a3a20ae0";

pub(super) fn is_displaydoc(unit: &Unit) -> bool {
    unit.target.proc_macro()
        && unit.pkg.name().as_str() == "displaydoc"
        && unit.pkg.version() == &semver::Version::new(0, 2, 5)
        && unit.pkg.summary().checksum() == Some(DISPLAYDOC_CHECKSUM)
}

fn supported_invocation(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    scripts: &HashMap<UnitHash, bool>,
) -> bool {
    unit.pkg.package_id().source_id().is_remote_registry()
        && unit.mode == CompileMode::Build
        && unit.target.is_lib()
        && !unit.target.proc_macro()
        && !unit
            .pkg
            .targets()
            .iter()
            .any(|target| target.is_custom_build())
        && unit.profile.rustflags.is_empty()
        && runner.bcx.extra_args_for(unit).is_none()
        && super::unit_rustflags_without_ohm_defaults(
            runner.bcx.gctx,
            runner.rustflags_for_cache_admission(unit),
        )
        .iter()
        .all(|flag| flag == super::OHM_EARLY_METADATA_RUSTFLAG)
        && runner.build_scripts.get(unit).is_none_or(|inputs| {
            inputs
                .to_link
                .iter()
                .chain(inputs.plugins.iter())
                .all(|(_, hash)| scripts.get(hash) == Some(&true))
        })
}

fn does_not_invoke_or_export_macros(unit: &Unit) -> bool {
    // The one-file 1.2.1 library imports four ICU types, derives only builtin
    // Clone/Copy and exports neither a macro nor any items imported from ICU.
    unit.target.is_lib()
        && unit.pkg.package_id().source_id().is_remote_registry()
        && unit.pkg.name().as_str() == "idna_adapter"
        && unit.pkg.version() == &semver::Version::new(1, 2, 1)
        && unit.pkg.summary().checksum()
            == Some("3acae9609540aa318d1bc588455225fb2085b9ed0c4f6bd0d9d5bcd86f1a0344")
}

#[derive(Clone, Copy, Eq, Ord, PartialEq, PartialOrd)]
pub(super) enum Exposure {
    Absent,
    OnlyThroughAdapter,
    MayInvoke,
}

/// Follow re-exports, including renamed derives and exported declarative macros.
pub(super) fn exposure(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    scripts: &HashMap<UnitHash, bool>,
    memo: &mut HashMap<Unit, Exposure>,
) -> Exposure {
    if let Some(&known) = memo.get(unit) {
        return known;
    }
    let inherited = runner
        .unit_deps(unit)
        .iter()
        .map(|dep| {
            if is_displaydoc(&dep.unit) {
                Exposure::MayInvoke
            } else {
                exposure(runner, &dep.unit, scripts, memo)
            }
        })
        .max()
        .unwrap_or(Exposure::Absent);
    let result = if inherited == Exposure::Absent {
        Exposure::Absent
    } else if !supported_invocation(runner, unit, scripts) {
        // An external compiler lookup, generated source or a linker search path
        // may bypass the adapter's ordinary Rust module boundary.
        Exposure::MayInvoke
    } else if does_not_invoke_or_export_macros(unit) {
        Exposure::OnlyThroughAdapter
    } else {
        inherited
    };
    memo.insert(unit.clone(), result);
    result
}

pub(super) fn verify(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    scripts: &HashMap<UnitHash, bool>,
    compiler: &[u8],
) -> bool {
    #[cfg(not(unix))]
    {
        let _ = (runner, unit, scripts, compiler);
        false
    }
    #[cfg(unix)]
    {
        verify_unix(runner, unit, scripts, compiler)
    }
}

#[cfg(unix)]
fn verify_unix(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    scripts: &HashMap<UnitHash, bool>,
    compiler: &[u8],
) -> bool {
    let checked = checked(runner, unit, scripts, compiler);
    tracing::debug!(target: "cargo::compiler::verified_macro_expansion", package = %unit.pkg.name(), ?checked);
    checked.unwrap_or(false)
}

#[cfg(unix)]
fn checked(
    runner: &BuildRunner<'_, '_>,
    unit: &Unit,
    scripts: &HashMap<UnitHash, bool>,
    compiler: &[u8],
) -> anyhow::Result<bool> {
    use anyhow::{Context as _, ensure};
    ensure!(
        supported_invocation(runner, unit, scripts),
        "unsupported compiler or build-script inputs"
    );
    let outputs = runner.outputs(unit)?;
    let metadata = outputs
        .iter()
        .find(|o| o.path.extension().is_some_and(|ext| ext == "rmeta"))
        .context("missing native metadata")?;
    let fingerprint = cargo_util::paths::read_regular_bounded(
        &runner.files().fingerprint_file_path(unit, ""),
        128,
    )?;
    let receipt = cache::Entry::new(
        runner.bcx.gctx.home().as_path_unlocked(),
        &metadata.path,
        unit.pkg
            .summary()
            .checksum()
            .context("missing registry checksum")?,
        &fingerprint,
        compiler,
    )
    .context("unavailable private expansion receipt")?;
    if receipt.contains() {
        tracing::debug!(target: "cargo::compiler::verified_macro_expansion", package = %unit.pkg.name(), "verified expansion receipt hit");
        return Ok(true);
    }
    let mut process = super::prepare_rustc(runner, unit).context("prepare native compiler")?;
    let mut args: Vec<_> = process.get_args().cloned().collect();
    ensure!(
        !args
            .iter()
            .any(|arg| arg.to_string_lossy().contains("incremental=")),
        "incremental rustc"
    );
    let index = args
        .iter()
        .position(|arg| arg == "--out-dir")
        .context("missing output directory")?;
    let temp = tempfile::Builder::new()
        .prefix(".macro-check-")
        .tempdir_in(runner.files().fingerprint_dir(unit))
        .context("temporary verification directory")?;
    *args.get_mut(index + 1).context("missing output path")? = temp.path().into();
    process.args_replace(&args).arg("-Zunpretty=expanded");
    use std::process::Stdio;
    let mut child = process
        .build_command()
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("expand crate with rustc")?;
    let stdout = child.stdout.take().context("missing compiler stdout")?;
    let stderr = child.stderr.take().context("missing compiler stderr")?;
    let (expanded, diagnostics) = std::thread::scope(|scope| {
        let stdout = scope.spawn(move || bounded_text(stdout, 32 * 1024 * 1024));
        let diagnostics = bounded_text(stderr, 128 * 1024);
        (stdout.join().ok().flatten(), diagnostics)
    });
    ensure!(child.wait()?.success(), "unsuccessful compiler expansion");
    let expanded = expanded.context("oversized or invalid compiler expansion")?;
    let diagnostics = diagnostics.context("oversized or invalid compiler diagnostic")?;
    ensure!(
        !expanded.is_empty()
            && diagnostics.lines().all(|line| {
                // rustc reports its temporary dep-info artifact even for unpretty output.
                serde_json::from_str::<serde_json::Value>(line)
                    .ok()
                    .is_some_and(|message| {
                        message.get("$message_type").and_then(|v| v.as_str()) == Some("artifact")
                            && message.get("emit").and_then(|v| v.as_str()) == Some("dep-info")
                            && message
                                .get("artifact")
                                .and_then(|v| v.as_str())
                                .map(std::path::Path::new)
                                .is_some_and(|path| {
                                    path.parent() == Some(temp.path())
                                        && path.extension().is_some_and(|ext| ext == "d")
                                })
                    })
            }),
        "diagnostics or empty expansion"
    );
    let tokens =
        TokenStream::from_str(&expanded).map_err(|_| anyhow::anyhow!("invalid expanded tokens"))?;
    Ok(only_simple_display_impls(tokens) && receipt.record())
}

/// Limit individual writes as well as a stream containing many short lines.
#[cfg(unix)]
fn bounded_text(reader: impl std::io::Read, limit: u64) -> Option<String> {
    use std::io::Read as _;
    let mut bytes = Vec::new();
    reader.take(limit + 1).read_to_end(&mut bytes).ok()?;
    if bytes.len() as u64 > limit {
        return None;
    }
    String::from_utf8(bytes).ok()
}

/// Every successful displaydoc 0.2.5 derive emits this absolute trait path and its input
/// type identifier. With at most one type argument, iterating its randomized generic-bound
/// map cannot permute two generated predicates. Ambiguous implementations fall back.
#[cfg(unix)]
fn only_simple_display_impls(tokens: TokenStream) -> bool {
    let mut pending = vec![tokens];
    while let Some(stream) = pending.pop() {
        let tokens: Vec<_> = stream.into_iter().collect();
        for (i, token) in tokens.iter().enumerate() {
            if let TokenTree::Group(group) = token {
                pending.push(group.stream());
            }
            if !matches!(token, TokenTree::Ident(name) if name == "Display") || i < 8 {
                continue;
            }
            let path = &tokens[i - 8..i];
            let colon = |t: &TokenTree| matches!(t, TokenTree::Punct(p) if p.as_char() == ':');
            if ![0, 1, 3, 4, 6, 7].iter().all(|&index| colon(&path[index]))
                || !matches!(&path[2], TokenTree::Ident(name) if name == "core")
                || !matches!(&path[5], TokenTree::Ident(name) if name == "fmt")
                || !matches!(tokens.get(i+1), Some(TokenTree::Ident(name)) if name == "for")
                || !matches!(tokens.get(i + 2), Some(TokenTree::Ident(_)))
                || !matches!(tokens.get(i+3), Some(TokenTree::Punct(p)) if p.as_char() == '<')
            {
                continue;
            }
            let Some(end) = tokens[i + 4..]
                .iter()
                .position(|tok| matches!(tok, TokenTree::Punct(p) if p.as_char() == '>'))
            else {
                return false;
            };
            if tokens[i+4..i+4+end].iter().any(|tok| matches!(tok, TokenTree::Punct(p) if p.as_char() == ',' || p.as_char() == '<')) {
                return false;
            }
        }
    }
    true
}

#[cfg(all(test, unix))]
mod tests {
    #[test]
    fn checks_the_display_impl_in_nested_expansion_output() {
        let simple = "const _: () = { impl<T> ::core::fmt::Display for Local<T> {} };";
        let multiple = "const _: () = { impl<T, U> ::core::fmt::Display for Local<T, U> {} };";
        assert!(super::only_simple_display_impls(simple.parse().unwrap()));
        assert!(!super::only_simple_display_impls(multiple.parse().unwrap()));
    }

    #[test]
    fn limits_a_single_line_and_rejects_invalid_utf8() {
        assert_eq!(
            super::bounded_text(&b"abcd"[..], 4).as_deref(),
            Some("abcd")
        );
        assert_eq!(super::bounded_text(&b"abcde"[..], 4), None);
        assert_eq!(super::bounded_text(&[0xff][..], 4), None);
    }
}
