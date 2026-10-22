use crate::command_prelude::*;
use std::path::PathBuf;

pub fn cli() -> Command {
    subcommand("gc")
        .about("Remove unused artifacts from Ohm build caches")
        .arg_dry_run("Show what would be removed without deleting any files")
        .arg(
            opt(
                "build-dir",
                "Collect only the specified shared build root",
            )
            .value_name("PATH")
            .value_parser(clap::value_parser!(PathBuf)),
        )
        .after_help(
            "Cleans obsolete shared build contexts and shared dependencies or ThinLTO objects \
             unused for at least one hour. After an Ohm upgrade, also removes obsolete private \
             intermediates from enrolled workspace targets. Skips active builds.\n\n\
             Run from any directory. Use `cargo clean` to remove the current project's build outputs.",
        )
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    cargo::workspace::build_cache_gc_roots::collect(
        gctx,
        args.get_one::<PathBuf>("build-dir")
            .map(|path| path.as_path()),
        args.dry_run(),
    )?;
    Ok(())
}
