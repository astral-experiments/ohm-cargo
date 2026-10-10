use crate::command_prelude::*;

use cargo::ops;

pub fn cli() -> Command {
    subcommand("check")
        // subcommand aliases are handled in aliased_command()
        // .alias("c")
        .about("Check a local package and all of its dependencies for errors")
        .arg(
            opt(
                "session",
                "Keep an experimental check session for SOURCE; press Enter to check again",
            )
            .value_name("SOURCE"),
        )
        .arg_future_incompat_report()
        .arg_message_format()
        .arg_silent_suggestion()
        .arg_package_spec(
            "Package(s) to check",
            "Check all packages in the workspace",
            "Exclude packages from the check",
        )
        .arg_targets_all(
            "Check only this package's library",
            "Check only the specified binary",
            "Check all binaries",
            "Check only the specified example",
            "Check all examples",
            "Check only the specified test target",
            "Check all targets that have `test = true` set",
            "Check only the specified bench target",
            "Check all targets that have `bench = true` set",
            "Check all targets",
        )
        .arg_features()
        .arg_parallel()
        .arg_release("Check artifacts in release mode, with optimizations")
        .arg_profile("Check artifacts with the specified profile")
        .arg_target_triple("Check for the target triple")
        .arg_target_dir()
        .arg_unit_graph()
        .arg_timings()
        .arg_compile_time_deps()
        .arg_manifest_path()
        .arg_ignore_rust_version()
        .after_help(color_print::cstr!(
            "Run `<bright-cyan,bold>cargo help check</>` for more detailed information.\n"
        ))
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    if let Some(source) = args.value_of_path("session", gctx) {
        if !gctx.cli_unstable().ohm_check_session {
            return Err(anyhow::anyhow!("--session requires -Zohm-check-session").into());
        }
        return session(gctx, args, source);
    }
    let ws = args.workspace(gctx)?;
    // This is a legacy behavior that causes `cargo check` to pass `--test`.
    let test = matches!(
        args.get_one::<String>("profile").map(String::as_str),
        Some("test")
    );
    let intent = UserIntent::Check { test };
    let compile_opts =
        args.compile_options(gctx, intent, Some(&ws), ProfileChecking::LegacyTestOnly)?;

    ops::compile(&ws, &compile_opts)?;
    Ok(())
}

fn session(gctx: &GlobalContext, args: &ArgMatches, source: std::path::PathBuf) -> CliResult {
    use cargo::compiler::Executor;
    use std::io::BufRead;
    use std::sync::Arc;

    if args.flag("unit-graph") || args.flag("compile-time-deps") {
        return Err(anyhow::anyhow!("check sessions require a complete terminal check").into());
    }
    let session = Arc::new(ops::check_session::CheckSession::new(source));
    let executor: Arc<dyn Executor> = session.clone();
    let input = std::io::stdin();
    let mut input = input.lock();
    loop {
        let fresh = gctx.fresh_for_check_session()?;
        let result = (|| -> cargo::util::CargoResult<()> {
            let ws = args.workspace(&fresh)?;
            let options = args.compile_options(
                &fresh,
                UserIntent::Check { test: false },
                Some(&ws),
                ProfileChecking::LegacyTestOnly,
            )?;
            ops::compile_with_exec(&ws, &options, &executor)?;
            Ok(())
        })();
        let succeeded = result.is_ok();
        if let Err(error) = result {
            // A failed root check may still own useful, query-tracked diagnostic state.
            cargo::display_error(&error, &mut fresh.shell());
        }
        let state = if session.is_warm() {
            "compiler retained"
        } else {
            "fresh checks"
        };
        fresh.shell().status(
            "Session",
            format!("{state}; press Enter to check again, or q / EOF to stop"),
        )?;
        let mut request = String::new();
        if input.read_line(&mut request)? == 0 || matches!(request.trim(), "q" | "quit") {
            return if succeeded {
                Ok(())
            } else {
                Err(CliError::code(101))
            };
        }
    }
}
