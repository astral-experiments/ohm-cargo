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
    let command = |name, about| {
        client(name, about).arg(
            Arg::new("args")
                .value_name("CARGO_ARGS")
                .value_parser(value_parser!(std::ffi::OsString))
                .num_args(0..)
                .allow_hyphen_values(true)
                .trailing_var_arg(true),
        )
    };
    subcommand("session")
        .about("Retain workspace command plans in a live server (experimental)")
        .subcommand_required(true)
        .arg_required_else_help(true)
        .subcommand(
            super::check::cli()
                .name("serve")
                .about("Serve workspace commands with default package, target, feature, and configuration options")
                .arg(socket_arg())
                .arg(opt("max-plans", "Maximum retained command preparations before releasing the arena")
                    .value_name("COUNT")
                    .default_value("16")
                    .value_parser(value_parser!(u16).range(1..=256)))
                .arg(opt("compiler-worker", "Use an explicitly built persistent rustc worker (experimental)")
                    .value_name("PATH")
                    .value_parser(value_parser!(std::path::PathBuf)))
                .after_help("The server stays in the foreground. Run `cargo session check`, `build`, `clippy`, `test`, or `bench` from the same directory and environment. SIGTERM lets the current command finish before shutdown; Ctrl-C also reaches compilers in the foreground process group."),
        )
        .subcommand(command("check", "Check packages using a retained command plan"))
        .subcommand(command("build", "Build packages using a retained command plan"))
        .subcommand(command("clippy", "Run Clippy with retained Cargo planning"))
        .subcommand(command("test", "Compile and execute tests, including doctests"))
        .subcommand(command("bench", "Compile and execute benchmarks"))
        .subcommand(client("status", "Show the running session's counters"))
        .subcommand(client("stop", "Stop the running session"))
}

#[cfg(unix)]
mod arguments;
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
    _configure: impl Fn(&mut GlobalContext, &ArgMatches) -> CliResult,
) -> CliResult {
    exec(gctx, args)
}

/// Clients preserve the launch identity; forwarded options configure the server.
/// Reject outer global options before Cargo configures the client context.
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
                matches!(id.as_str(), "socket" | "json" | "args")
                    || args.value_source(id.as_str())
                        != Some(clap::parser::ValueSource::CommandLine),
                "session clients accept only --socket and --json; pass `{id}` to `cargo session serve`"
            );
        }
    }
    Ok(())
}
