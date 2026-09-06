use crate::command_prelude::*;

fn socket_arg() -> Arg {
    opt("socket", "Path to the session's Unix socket")
        .value_name("PATH")
        .value_parser(value_parser!(std::path::PathBuf))
}

pub fn cli() -> Command {
    let client = |name, about| {
        subcommand(name)
            .about(about)
            .arg(socket_arg())
            .arg(flag("json", "Print the session response as JSON"))
    };
    subcommand("session")
        .about("Reuse Cargo's check planning in a live server (experimental)")
        .subcommand_required(true)
        .arg_required_else_help(true)
        .subcommand(
            super::check::cli()
                .name("serve")
                .about("Serve checks with fixed package, target, feature, and configuration options")
                .arg(socket_arg())
                .after_help("The server stays in the foreground. Run `cargo session check` from the same directory and environment to check again. SIGTERM lets the current check finish before shutdown; Ctrl-C also reaches compilers in the foreground process group."),
        )
        .subcommand(client("check", "Check using the running session's options"))
        .subcommand(client("status", "Show the running session's counters"))
        .subcommand(client("stop", "Stop the running session"))
}

#[cfg(unix)]
mod client;
#[cfg(unix)]
mod output;
#[cfg(unix)]
mod protocol;
#[cfg(unix)]
mod server;
#[cfg(unix)]
mod transport;

#[cfg(unix)]
pub(crate) use client::Client;
#[cfg(unix)]
pub use client::exec;
#[cfg(unix)]
pub use server::serve;

#[cfg(not(unix))]
pub fn exec(_gctx: &mut GlobalContext, _args: &ArgMatches) -> CliResult {
    Err(anyhow::anyhow!("`cargo session` currently requires Unix").into())
}

#[cfg(not(unix))]
pub fn serve(
    gctx: &mut GlobalContext,
    args: &ArgMatches,
    _configure: impl Fn(&mut GlobalContext) -> CliResult,
) -> CliResult {
    exec(gctx, args)
}

/// Client commands select an existing fixed configuration through their socket.
/// Reject command-line overrides before Cargo configures the client context.
pub fn validate_client_options(
    root_args: &ArgMatches,
    session_args: &ArgMatches,
) -> cargo::CargoResult<()> {
    let (_, client_args) = session_args
        .subcommand()
        .expect("session requires a subcommand");
    for args in [root_args, client_args] {
        for id in args.ids() {
            anyhow::ensure!(
                matches!(id.as_str(), "socket" | "json")
                    || args.value_source(id.as_str())
                        != Some(clap::parser::ValueSource::CommandLine),
                "session clients accept only --socket and --json; pass `{id}` to `cargo session serve`"
            );
        }
    }
    Ok(())
}
