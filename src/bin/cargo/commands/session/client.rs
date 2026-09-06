//! A client only sends a command and renders its completed response.

use super::protocol::{self, ClientIdentity, Operation, Request};
use super::transport;
use crate::command_prelude::*;
use anyhow::Context as _;
use std::os::unix::net::UnixStream;

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    let (command, args) = args.subcommand().expect("session requires a subcommand");
    let command = match command {
        "check" => Operation::Check,
        "status" => Operation::Status,
        "stop" => Operation::Stop,
        "serve" => unreachable!("session serve is dispatched with its configuration"),
        _ => unreachable!("unexpected session subcommand"),
    };
    let path = transport::socket_path(gctx, args)?;
    let mut connection = UnixStream::connect(&path)
        .with_context(|| format!("could not connect to Cargo session at {}", path.display()))?;
    let request = Request {
        version: protocol::VERSION,
        command,
        identity: ClientIdentity::new(gctx)?,
    };
    protocol::write_request(&mut connection, &request)?;
    // Never retry a transport failure: the command may already have executed.
    let response = protocol::read_response(connection)?;
    if args.get_flag("json") {
        gctx.shell().print_json(&response)?;
    } else if matches!(command, Operation::Check) || response.returncode != 0 {
        gctx.shell().print_ansi_stdout(response.stdout.as_bytes())?;
        gctx.shell().print_ansi_stderr(response.stderr.as_bytes())?;
    } else {
        let mut shell = gctx.shell();
        serde_json::to_writer_pretty(shell.out(), &response)
            .context("could not serialize Cargo session response")?;
        writeln!(shell.out())?;
    }
    if response.returncode != 0 {
        return Err(CliError::code(response.returncode));
    }
    Ok(())
}
