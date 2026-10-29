use crate::command_prelude::*;
use anyhow::Context as _;
use std::path::PathBuf;
use std::time::Duration;

pub fn cli() -> Command {
    subcommand("gc")
        .about("Remove unused artifacts from Ohm build caches")
        .arg_dry_run("Show what would be removed without deleting any files")
        .arg(
            opt("max-age", "Remove artifacts unused for at least this duration")
                .value_name("DURATION")
                .default_value("1hr")
                .value_parser(parse_max_age),
        )
        .arg(
            opt(
                "build-dir",
                "Collect only the specified shared build root",
            )
            .value_name("PATH")
            .value_parser(clap::value_parser!(PathBuf)),
        )
        .after_help(
            "Applies --max-age to workspace targets, shared compiler contexts, dependency builds, \
             and ThinLTO objects. Examples: 30min, 1hr, 2d. Obsolete compiler contexts and legacy \
             caches are eligible immediately. Skips active builds.\n\n\
             Run from any directory. Use `cargo clean` to remove the current project's build outputs.",
        )
}

fn parse_max_age(value: &str) -> cargo::CargoResult<Duration> {
    let duration = value
        .parse::<jiff::Span>()?
        .to_duration(jiff::SpanRelativeTo::days_are_24_hours())
        .context("use a fixed duration, such as 30min, 1hr, or 2d")?;
    duration.try_into().context("duration must be non-negative")
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    cargo::workspace::build_cache_gc_roots::collect(
        gctx,
        args.get_one::<PathBuf>("build-dir")
            .map(|path| path.as_path()),
        args.dry_run(),
        *args.get_one::<Duration>("max-age").unwrap(),
    )?;
    Ok(())
}
