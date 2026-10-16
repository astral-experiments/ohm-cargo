use crate::command_prelude::*;
use std::path::PathBuf;

pub fn cli() -> Command {
    subcommand("gc")
        .about("Remove unused artifacts from Ohm shared build caches")
        .arg_dry_run("Show what would be removed without deleting any files")
        .arg(
            opt(
                "build-dir",
                "Collect one shared build root instead of all known and discovered roots",
            )
            .value_name("PATH")
            .value_parser(clap::value_parser!(PathBuf)),
        )
        .after_help(
            "Explicitly reclaims legacy caches, contexts from older Ohm releases or removed \
             compilers, and dependencies or build contexts unused for at least one hour, \
             respecting active builds. \
             Runs from any directory.\n\n\
             Use `cargo clean` to remove the current project's outputs and private build state.",
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
