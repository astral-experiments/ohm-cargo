//! A client only sends a command and renders its completed response.

use super::protocol::{self, ClientIdentity, Operation, Request};
use super::transport;
use crate::command_prelude::*;
use anyhow::Context as _;
use std::ffi::OsString;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::net::UnixStream;
use std::path::PathBuf;

pub(crate) struct Client {
    command: Operation,
    socket: Option<PathBuf>,
    json: bool,
}

impl Client {
    /// Recognize unambiguous literal clients without constructing Cargo's CLI.
    /// All other invocations retain clap's parsing, diagnostics, and alias handling.
    pub(crate) fn parse(mut args: impl Iterator<Item = OsString>) -> Option<Self> {
        if args.next()? != "session" {
            return None;
        }
        let command = match args.next()?.to_str()? {
            "check" => Operation::Check,
            "status" => Operation::Status,
            "stop" => Operation::Stop,
            _ => return None,
        };
        let mut client = Self {
            command,
            socket: None,
            json: false,
        };
        while let Some(arg) = args.next() {
            if arg == "--json" && !client.json {
                client.json = true;
            } else if arg == "--socket" && client.socket.is_none() {
                let path = args.next()?;
                if path.is_empty() || path.as_bytes().starts_with(b"-") {
                    return None;
                }
                client.socket = Some(path.into());
            } else if let Some(path) = arg.as_bytes().strip_prefix(b"--socket=") {
                if path.is_empty() || client.socket.is_some() {
                    return None;
                }
                client.socket = Some(std::ffi::OsStr::from_bytes(path).into());
            } else {
                return None;
            }
        }
        Some(client)
    }

    pub(crate) fn exec(self, gctx: &mut GlobalContext) -> CliResult {
        let path = transport::socket_path_for(gctx.cwd(), self.socket.as_deref())?;
        let mut connection = UnixStream::connect(&path)
            .with_context(|| format!("could not connect to Cargo session at {}", path.display()))?;
        let request = Request {
            version: protocol::VERSION,
            command: self.command,
            identity: ClientIdentity::new(gctx)?,
        };
        protocol::write_request(&mut connection, &request)?;
        // Never retry a transport failure: the command may already have executed.
        let response = protocol::read_response(connection)?;
        if self.json {
            gctx.shell().print_json(&response)?;
        } else if matches!(self.command, Operation::Check) || response.returncode != 0 {
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
}

pub fn exec(gctx: &mut GlobalContext, args: &ArgMatches) -> CliResult {
    let (command, args) = args.subcommand().expect("session requires a subcommand");
    let command = match command {
        "check" => Operation::Check,
        "status" => Operation::Status,
        "stop" => Operation::Stop,
        "serve" => unreachable!("session serve is dispatched with its configuration"),
        _ => unreachable!("unexpected session subcommand"),
    };
    Client {
        command,
        socket: args.get_one::<PathBuf>("socket").cloned(),
        json: args.get_flag("json"),
    }
    .exec(gctx)
}
