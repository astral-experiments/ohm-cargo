//! Versioned messages and bounded framing for one command per connection.

use anyhow::{Context as _, ensure};
use cargo::CargoResult;
use cargo::util::GlobalContext;
use cargo_util::Sha256;
use serde::{Deserialize, Serialize};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::time::{SystemTime, UNIX_EPOCH};

pub(super) const VERSION: u32 = 1;
pub(super) const MAX_REQUEST_BYTES: usize = 1024 * 1024;
const MAX_RESPONSE_BYTES: usize = 64 * 1024 * 1024;

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub(super) enum Operation {
    Check,
    Status,
    Stop,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Request {
    pub version: u32,
    pub command: Operation,
    pub identity: ClientIdentity,
}

/// Identity uses the launch environment, before Cargo initializes libraries.
/// Values are hashed rather than copied into the protocol. Program metadata
/// detects a replaced Cargo binary without hashing the executable per request.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ClientIdentity {
    cwd: Vec<u8>,
    environment: String,
    cargo: ExecutableIdentity,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct ExecutableIdentity {
    path: Vec<u8>,
    version: String,
    device: u64,
    inode: u64,
    length: u64,
    modified_seconds: i64,
    modified_nanoseconds: i64,
    changed_seconds: i64,
    changed_nanoseconds: i64,
}

impl ClientIdentity {
    pub(super) fn new(gctx: &GlobalContext) -> CargoResult<Self> {
        let cwd = gctx.cwd().canonicalize()?.as_os_str().as_bytes().to_vec();
        // Cargo supplies its own executable and jobserver transport to build
        // processes. Every other launch variable can be a build-script input.
        let mut variables: Vec<_> = gctx
            .env_os()
            .filter(|(key, _)| !matches!(key.to_str(), Some("CARGO" | "CARGO_MAKEFLAGS")))
            .collect();
        variables.sort_unstable();
        let mut hash = Sha256::new();
        for (key, value) in variables {
            for bytes in [key.as_bytes(), value.as_bytes()] {
                hash.update(&(bytes.len() as u64).to_le_bytes());
                hash.update(bytes);
            }
        }
        let path = std::env::current_exe()?.canonicalize()?;
        let metadata = path.metadata()?;
        Ok(Self {
            cwd,
            environment: hash.finish_hex(),
            cargo: ExecutableIdentity {
                path: path.as_os_str().as_bytes().to_vec(),
                version: cargo::version().to_string(),
                device: metadata.dev(),
                inode: metadata.ino(),
                length: metadata.len(),
                modified_seconds: metadata.mtime(),
                modified_nanoseconds: metadata.mtime_nsec(),
                changed_seconds: metadata.ctime(),
                changed_nanoseconds: metadata.ctime_nsec(),
            },
        })
    }
}

#[derive(Clone, Deserialize, Serialize)]
pub(super) struct SessionInfo {
    pub id: String,
    pub identity: ClientIdentity,
    pub configuration: SessionConfiguration,
}

/// The recorded invocation describes the fixed options selected by this socket.
/// Execution uses the already expanded clap arguments and configuration factory.
#[derive(Clone, Deserialize, Serialize)]
pub(super) struct SessionConfiguration {
    pub command: Vec<String>,
}

impl SessionInfo {
    pub(super) fn new(gctx: &GlobalContext) -> CargoResult<Self> {
        let identity = ClientIdentity::new(gctx)?;
        let arguments: Vec<_> = std::env::args_os().skip(1).collect();
        let mut hash = Sha256::new();
        hash.update(&serde_json::to_vec(&identity)?);
        for argument in &arguments {
            let bytes = argument.as_bytes();
            hash.update(&(bytes.len() as u64).to_le_bytes());
            hash.update(bytes);
        }
        hash.update(&std::process::id().to_le_bytes());
        hash.update(
            &SystemTime::now()
                .duration_since(UNIX_EPOCH)?
                .as_nanos()
                .to_le_bytes(),
        );
        Ok(Self {
            id: hash.finish_hex(),
            identity,
            configuration: SessionConfiguration {
                command: arguments
                    .iter()
                    .map(|argument| argument.to_string_lossy().into_owned())
                    .collect(),
            },
        })
    }
}

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum ResponseStatus {
    Complete,
    Rejected,
    Failed,
    Cancelled,
}

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum ErrorKind {
    Protocol,
    Identity,
    InputsChanged,
    OutputLimit,
    Internal,
    ShuttingDown,
}

#[derive(Deserialize, Serialize)]
pub(super) struct Response {
    pub version: u32,
    pub session: SessionInfo,
    pub status: ResponseStatus,
    pub error_kind: Option<ErrorKind>,
    pub pid: u32,
    pub checks: u64,
    pub preparations: u64,
    pub revision: u64,
    pub reprepare_reason: Option<String>,
    pub reuse_disabled_reason: Option<String>,
    pub reused: bool,
    pub compiler_worker: Option<cargo::util::session_worker::WorkerStats>,
    pub returncode: i32,
    pub elapsed_ms: f64,
    pub stdout: String,
    pub stderr: String,
}

pub(super) fn read_request(reader: impl Read) -> CargoResult<Request> {
    let bytes = read_frame(reader, MAX_REQUEST_BYTES, "request")?;
    validate_version(&bytes)?;
    serde_json::from_slice(&bytes).context("invalid session request")
}

pub(super) fn write_request(writer: impl Write, request: &Request) -> CargoResult<()> {
    write_frame(writer, request, MAX_REQUEST_BYTES, "request")
}

pub(super) fn read_response(reader: impl Read) -> CargoResult<Response> {
    let bytes = read_frame(reader, MAX_RESPONSE_BYTES, "response")?;
    validate_version(&bytes)?;
    serde_json::from_slice(&bytes).context("invalid session response")
}

pub(super) fn write_response(writer: impl Write, response: &Response) -> CargoResult<()> {
    write_frame(writer, response, MAX_RESPONSE_BYTES, "response")
}

fn validate_version(bytes: &[u8]) -> CargoResult<()> {
    #[derive(Deserialize)]
    struct Header {
        version: u32,
    }
    let header: Header =
        serde_json::from_slice(bytes).context("invalid session protocol header")?;
    ensure!(
        header.version == VERSION,
        "unsupported protocol version {}; expected {VERSION}",
        header.version
    );
    Ok(())
}

fn read_frame(reader: impl Read, limit: usize, kind: &str) -> CargoResult<Vec<u8>> {
    let mut bytes = Vec::new();
    BufReader::new(reader)
        .take(limit as u64 + 1)
        .read_until(b'\n', &mut bytes)?;
    ensure!(bytes.len() <= limit, "session {kind} exceeds {limit} bytes");
    ensure!(
        bytes.last() == Some(&b'\n'),
        "incomplete session {kind} frame"
    );
    Ok(bytes)
}

fn write_frame(
    mut writer: impl Write,
    value: &impl Serialize,
    limit: usize,
    kind: &str,
) -> CargoResult<()> {
    // Bound serialization as well as reading. Leave one byte for the delimiter.
    struct Frame {
        bytes: Vec<u8>,
        limit: usize,
    }
    impl Write for Frame {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            if bytes.len() > self.limit.saturating_sub(self.bytes.len()) {
                return Err(io::Error::other("session frame exceeds its size limit"));
            }
            self.bytes.extend_from_slice(bytes);
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    let mut frame = Frame {
        bytes: Vec::new(),
        limit: limit - 1,
    };
    serde_json::to_writer(&mut frame, value)
        .with_context(|| format!("could not serialize session {kind}"))?;
    frame.bytes.push(b'\n');
    writer.write_all(&frame.bytes)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn response_framing_is_bounded_and_preserves_escaped_output() {
        let value = serde_json::json!({"output": "a\nb\u{0}c\\d"});
        let mut bytes = Vec::new();
        write_frame(&mut bytes, &value, 128, "response").unwrap();
        let decoded = read_frame(bytes.as_slice(), 128, "response").unwrap();
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&decoded).unwrap(),
            value
        );
        assert!(write_frame(Vec::new(), &value, 8, "response").is_err());
        assert!(read_frame(b"12345678\n".as_slice(), 8, "response").is_err());
        assert!(read_frame(b"{}".as_slice(), 128, "response").is_err());
    }
}
