use crate::command_prelude::*;
use cargo::core::Workspace;
use cargo::ops;

pub fn cli() -> Command {
    subcommand("test")
        // Subcommand aliases are handled in `aliased_command()`.
        // .alias("t")
        .about("Execute all unit and integration tests and build examples of a local package")
        .arg(
            Arg::new("TESTNAME")
                .action(ArgAction::Set)
                .help("If specified, only run tests containing this string in their names"),
        )
        .arg(
            Arg::new("args")
                .value_name("ARGS")
                .help("Arguments for the test binary")
                .num_args(0..)
                .last(true),
        )
        .arg(flag("no-run", "Compile, but don't run tests"))
        .arg(flag("no-fail-fast", "Run all tests regardless of failure"))
        .arg_future_incompat_report()
        .arg_message_format()
        .arg(
            flag(
                "quiet",
                "Display one character per test instead of one line",
            )
            .short('q'),
        )
        .arg_package_spec(
            "Package to run tests for",
            "Test all packages in the workspace",
            "Exclude packages from the test",
        )
        .arg_targets_all(
            "Test only this package's library",
            "Test only the specified binary",
            "Test all binaries",
            "Test only the specified example",
            "Test all examples",
            "Test only the specified test target",
            "Test all targets that have `test = true` set",
            "Test only the specified bench target",
            "Test all targets that have `bench = true` set",
            "Test all targets (does not include doctests)",
        )
        .arg(
            flag("doc", "Test only this library's documentation")
                .help_heading(heading::TARGET_SELECTION),
        )
        .arg_features()
        .arg_jobs()
        .arg_unsupported_keep_going()
        .arg_release("Build artifacts in release mode, with optimizations")
        .arg_profile("Build artifacts with the specified profile")
        .arg_target_triple("Build for the target triple")
        .arg_target_dir()
        .arg_unit_graph()
        .arg_timings()
        .arg_manifest_path()
        .arg_ignore_rust_version()
        .after_help(color_print::cstr!(
            "Run `<bright-cyan,bold>cargo help test</>` for more detailed information.\n\
             Run `<bright-cyan,bold>cargo test -- --help</>` for test binary options.\n",
        ))
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    let ws = args.workspace(gctx)?;
    let (options, test_args) = options(gctx, args, &ws)?;
    let test_args = test_args.iter().map(String::as_str).collect::<Vec<_>>();
    ops::run_tests(&ws, &options, &test_args)
}

pub(super) fn options(
    gctx: &GlobalContext,
    args: &ArgMatches,
    ws: &Workspace<'_>,
) -> Result<(ops::TestOptions, Vec<String>), CliError> {
    let mut compile_opts =
        args.compile_options(gctx, UserIntent::Test, Some(ws), ProfileChecking::Custom)?;

    compile_opts.build_config.requested_profile =
        args.get_profile_name("test", ProfileChecking::Custom)?;

    // `TESTNAME` is actually an argument of the test binary, but it's
    // important, so we explicitly mention it and reconfigure.
    let test_name = args.get_one::<String>("TESTNAME");
    let test_args = args.get_one::<String>("TESTNAME").into_iter();
    let test_args = test_args.chain(args.get_many::<String>("args").unwrap_or_default());
    let test_args = test_args.map(String::as_str).collect::<Vec<_>>();

    let no_run = args.flag("no-run");
    let doc = args.flag("doc");
    if doc {
        if compile_opts.filter.is_specific() {
            return Err(
                anyhow::format_err!("can't mix --doc with other target selecting options").into(),
            );
        }
        if no_run {
            return Err(anyhow::format_err!("can't skip running doc tests with --no-run").into());
        }
        compile_opts.build_config.intent = UserIntent::Doctest;
        compile_opts.filter = ops::CompileFilter::lib_only();
    } else if test_name.is_some() && !compile_opts.filter.is_specific() {
        // If arg `TESTNAME` is provided, assumed that the user knows what
        // exactly they wants to test, so we use `all_test_targets` to
        // avoid compiling unnecessary targets such as examples, which are
        // included by the logic of default target filter.
        compile_opts.filter = ops::CompileFilter::all_test_targets();
    }

    // Focus only an explicitly selected, exact, built-in library test. The Ohm
    // compiler's `-Ztest-harness-filter` keeps separate per-filter artifacts and
    // may omit backend diagnostics for tests outside the focused harness.
    if gctx.cli_unstable().ohm_focused_tests
        && !no_run
        && !doc
        && compile_opts.target_rustc_args.is_none()
        && compile_opts.build_config.requested_kinds.len() == 1
        && test_name.is_some_and(|name| name.contains("::"))
        && matches!(test_args.as_slice(), [_, "--exact"])
        && matches!(
            &compile_opts.filter,
            ops::CompileFilter::Only {
                all_targets: false,
                lib: ops::LibRule::True,
                bins: ops::FilterRule::Just(bins),
                examples: ops::FilterRule::Just(examples),
                tests: ops::FilterRule::Just(tests),
                benches: ops::FilterRule::Just(benches),
            } if bins.is_empty()
                && examples.is_empty()
                && tests.is_empty()
                && benches.is_empty()
        )
        && matches!(&compile_opts.spec, ops::Packages::Packages(packages) if packages.len() == 1)
        && compile_opts.spec.get_packages(ws).is_ok_and(|packages| {
            packages.len() == 1
                && packages[0]
                    .targets()
                    .iter()
                    .any(|target| target.is_lib() && target.harness())
        })
    {
        compile_opts.target_rustc_args =
            Some(vec![format!("-Ztest-harness-filter={}", test_args[0])]);
    }

    let ops = ops::TestOptions {
        no_run,
        no_fail_fast: args.flag("no-fail-fast"),
        compile_opts,
    };

    Ok((ops, test_args.into_iter().map(str::to_owned).collect()))
}
