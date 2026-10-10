use crate::command_prelude::*;

pub fn cli() -> Command {
    subcommand("stop")
        .about("Stop this workspace's experimental check session")
        .arg_manifest_path()
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    #[cfg(not(unix))]
    {
        let _ = (gctx, args);
        Err(anyhow::anyhow!("workspace check sessions currently require Unix").into())
    }
    #[cfg(unix)]
    {
        let ws = args.workspace(gctx)?;
        let stopped = cargo::ops::check_session::workspace::stop(ws.root())?;
        gctx.shell()
            .status("Session", if stopped { "stopped" } else { "not running" })?;
        Ok(())
    }
}
