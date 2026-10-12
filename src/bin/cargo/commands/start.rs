use crate::command_prelude::*;

pub fn cli() -> Command {
    super::check::cli()
        .name("start")
        .about("Start and warm an experimental workspace check session")
        .arg(opt("source", "Source file whose supported edits may reuse compiler state")
            .value_name("SOURCE").required(true))
        .mut_arg("no-session", |arg| arg.hide(true).conflicts_with("source"))
        .after_help("Requires -Zohm-check-session. Subsequent cargo check commands use the session; cargo stop shuts it down.")
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    if !gctx.cli_unstable().ohm_check_session {
        return Err(anyhow::anyhow!("cargo start requires -Zohm-check-session").into());
    }
    #[cfg(not(unix))]
    {
        let _ = args;
        Err(anyhow::anyhow!("workspace check sessions currently require Unix").into())
    }
    #[cfg(unix)]
    {
        if args.flag("unit-graph") || args.flag("compile-time-deps") {
            return Err(anyhow::anyhow!("cargo start requires a complete check").into());
        }
        let source = args.value_of_path("source", gctx).unwrap();
        let ws = args.workspace(gctx)?;
        let info = cargo::ops::check_session::workspace::start(ws.root(), &source)?;
        gctx.shell().status(
            "Session",
            format!(
                "workspace host pid={}; cargo check reuses it, cargo stop shuts it down",
                info.pid
            ),
        )?;
        drop(ws);
        // A failed first check leaves the explicit session available for a repair.
        super::check::exec(gctx, args)
    }
}
