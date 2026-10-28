use crate::command_prelude::*;
use cargo::ops::{self, WorktreeOptions};
use std::path::PathBuf;

pub fn cli() -> Command {
    subcommand("worktree")
        .about("Create Git worktrees with seeded build state (experimental Ohm command)")
        .subcommand_required(true)
        .arg_required_else_help(true)
        .subcommand(
            subcommand("add")
                .about("Create a Git worktree and seed compatible build state from this workspace")
                .arg(
                    opt("branch", "Create a new branch for the worktree")
                        .short('b')
                        .value_name("BRANCH"),
                )
                .arg(
                    flag("detach", "Detach HEAD in the new worktree")
                        .short('d')
                        .conflicts_with("branch"),
                )
                .arg(
                    Arg::new("path")
                        .value_name("PATH")
                        .help("Directory for the new worktree")
                        .value_parser(value_parser!(PathBuf))
                        .required(true),
                )
                .arg(
                    Arg::new("commit")
                        .value_name("COMMIT")
                        .help("Commit or branch to check out"),
                )
                .arg(
                    opt(
                        "destination-target-dir",
                        "Destination target directory (defaults to <new-workspace>/target)",
                    )
                    .long("target-dir")
                    .value_name("DIRECTORY")
                    .value_parser(value_parser!(PathBuf)),
                )
                .arg_manifest_path(),
        )
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    if !gctx.cli_unstable().ohm_defaults() {
        return Err(anyhow::format_err!(
            "`cargo worktree` is an experimental Ohm command; \
             enable Ohm defaults with `-Zohm-defaults=yes`"
        )
        .into());
    }

    match args.subcommand() {
        Some(("add", args)) => {
            let opts = WorktreeOptions {
                manifest_path: args.root_manifest(gctx)?,
                path: args.get_one::<PathBuf>("path").unwrap().clone(),
                branch: args.get_one::<String>("branch").cloned(),
                detach: args.get_flag("detach"),
                commit: args.get_one::<String>("commit").cloned(),
                target_dir: args.get_one::<PathBuf>("destination-target-dir").cloned(),
            };
            ops::worktree_add(gctx, &opts)?;
            Ok(())
        }
        Some((cmd, _)) => unreachable!("unexpected command {cmd}"),
        None => unreachable!("expected a worktree subcommand"),
    }
}
