//! QA-only bridge to a separate, policy-bound native freshness checker. A refused query tail-execs stock Wild.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::ffi::{CStr, CString, OsStr, OsString};
use std::fmt::Write as _;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const CAPSULE: &str = "/run/ohm-native-handoff-v1";
const STOCK_SHA: &str = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5";

fn hex(b: &[u8]) -> String {
    let mut s = String::with_capacity(b.len() * 2);
    for v in b {
        write!(&mut s, "{v:02x}").unwrap()
    }
    s
}
fn valid_digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn sha_file(p: &Path) -> io::Result<String> {
    let mut h = Sha256::new();
    io::copy(&mut File::open(p)?, &mut h)?;
    Ok(hex(&h.finalize()))
}
fn raw_env_sha() -> String {
    let mut env: Vec<_> = std::env::vars_os().collect();
    env.sort();
    let mut h = Sha256::new();
    for (k, v) in env {
        h.update(k.as_bytes());
        h.update(b"=");
        h.update(v.as_bytes());
        h.update([0]);
    }
    hex(&h.finalize())
}
fn mem_file(name: &CStr) -> io::Result<File> {
    let fd =
        unsafe { libc::memfd_create(name.as_ptr(), libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn proc_parent(pid: i32) -> io::Result<i32> {
    fs::read_to_string(format!("/proc/{pid}/status"))?
        .lines()
        .find_map(|l| l.strip_prefix("PPid:")?.trim().parse().ok())
        .ok_or_else(|| io::Error::other("missing ancestor"))
}
fn stamp(p: &Path, mode: u64) -> io::Result<[i128; 9]> {
    let m = p.symlink_metadata()?;
    let c = CString::new(p.as_os_str().as_bytes())?;
    if !m.is_file()
        || m.mode() as u64 & 0o7777 != mode
        || m.nlink() != 1
        || m.uid() != unsafe { libc::geteuid() }
        || unsafe { libc::llistxattr(c.as_ptr(), std::ptr::null_mut(), 0) } != 0
    {
        return Err(io::Error::other("unsupported incumbent"));
    }
    Ok([
        m.dev() as i128,
        m.ino() as i128,
        m.mode() as i128,
        m.uid() as i128,
        m.size() as i128,
        m.mtime() as i128,
        m.mtime_nsec() as i128,
        m.ctime() as i128,
        m.ctime_nsec() as i128,
    ])
}
fn text<'a>(v: &'a Value, k: &str) -> io::Result<&'a str> {
    v.get(k)
        .and_then(Value::as_str)
        .ok_or_else(|| io::Error::other("missing policy field"))
}
fn check(
    capsule: &Path,
    policy: &Value,
    argv: &[OsString],
    target: &Path,
    nonce: &str,
    log: &mut Value,
) -> io::Result<&'static str> {
    if policy["schema"] != 1
        || text(policy, "wild_sha256")? != STOCK_SHA
        || sha_file(&capsule.join("check"))? != text(policy, "checker_sha256")?
    {
        return Ok("capsule-identity");
    }
    if std::env::consts::OS != "linux"
        || std::env::consts::ARCH != "x86_64"
        || unsafe { libc::getuid() } != unsafe { libc::geteuid() }
        || unsafe { libc::geteuid() } == 0
    {
        return Ok("host");
    }
    if argv
        .iter()
        .any(|s| s.as_bytes().starts_with(b"--threads") || s.as_bytes().starts_with(b"@"))
        || std::env::vars_os().any(|(k, _)| {
            k.as_bytes().starts_with(b"WILD_") || k == "LD_PRELOAD" || k == "LD_AUDIT"
        })
    {
        return Ok("explicit-native-override");
    }
    let mode = policy["required_mode"]
        .as_u64()
        .ok_or_else(|| io::Error::other("mode"))?;
    let before = stamp(target, mode)?;
    log["before"] = json!(before);
    let pid = unsafe { libc::getppid() };
    let gcc = proc_parent(pid)?;
    let collect_sha = sha_file(Path::new(&format!("/proc/{pid}/exe")))?;
    let gcc_sha = sha_file(Path::new(&format!("/proc/{gcc}/exe")))?;
    if collect_sha != text(policy, "collect2_sha256")? || gcc_sha != text(policy, "gcc_sha256")? {
        return Ok("driver-chain");
    }
    let client = unsafe { jobserver::Client::from_env() }
        .ok_or_else(|| io::Error::other("missing pipe jobserver"))?;
    let mut tokens = Vec::new();
    while let Some(t) = client.try_acquire()? {
        tokens.push(t);
        if tokens.len() >= 16 {
            return Ok("width-above-16");
        }
    }
    let workers = tokens.len() + 1;
    log["workers"] = json!(workers);
    let Some(cert) = policy["workers"].get(workers.to_string()) else {
        return Ok("untrained-width");
    };
    let train = text(cert, "training_sha256")?;
    let image = text(cert, "output_blake3")?;
    if !valid_digest(train) || !valid_digest(image) {
        return Ok("invalid-training-policy");
    }
    let req = serde_json::to_vec(
        &json!({"schema":1,"nonce":nonce,"workers":workers,"training_sha256":train,"cwd_hex":hex(std::env::current_dir()?.as_os_str().as_bytes()),
        "argv_hex":argv.iter().map(|s|hex(s.as_bytes())).collect::<Vec<_>>(),"env_sha256":raw_env_sha(),"gcc_sha256":gcc_sha,"collect2_sha256":collect_sha}),
    )?;
    let req_sha = hex(&Sha256::digest(&req));
    log["request_sha256"] = json!(req_sha);
    log["training_sha256"] = json!(train);
    let mut input = mem_file(c"ohm-native-check-request")?;
    input.write_all(&req)?;
    input.rewind()?;
    if unsafe {
        libc::fcntl(
            input.as_raw_fd(),
            libc::F_ADD_SEALS,
            libc::F_SEAL_WRITE | libc::F_SEAL_GROW | libc::F_SEAL_SHRINK | libc::F_SEAL_SEAL,
        )
    } < 0
    {
        return Ok("cannot-seal-request");
    }
    let mut reply = mem_file(c"ohm-native-check-response")?;
    let err = mem_file(c"ohm-native-check-diagnostics")?;
    let mut child = Command::new(capsule.join("check"))
        .stdin(Stdio::from(input))
        .stdout(Stdio::from(reply.try_clone()?))
        .stderr(Stdio::from(err.try_clone()?))
        .process_group(0)
        .spawn()?;
    let deadline = Instant::now() + Duration::from_secs(8);
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if Instant::now() >= deadline {
            unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL) };
            let _ = child.wait();
            return Ok("checker-timeout");
        }
        std::thread::sleep(Duration::from_millis(2));
    };
    log["checker_code"] = json!(status.code());
    if !status.success() || err.metadata()?.len() != 0 || reply.metadata()?.len() > 512 {
        return Ok("checker-refusal");
    }
    reply.rewind()?;
    let mut line = String::new();
    reply.take(513).read_to_string(&mut line)?;
    if line != format!("OHM-NATIVE-FRESH-1 {nonce} {req_sha} {train} {image} {workers}\n") {
        return Ok("invalid-response");
    }
    if stamp(target, mode)? != before {
        return Ok("incumbent-changed");
    }
    log["output_blake3"] = json!(image);
    Ok("fixture-native-fresh")
}
fn try_select(capsule: &Path, argv: &[OsString]) -> io::Result<bool> {
    let mut outs = argv
        .windows(2)
        .filter_map(|p| (p[0] == OsStr::new("-o")).then(|| Path::new(&p[1])));
    let Some(target) = outs.next() else {
        return Ok(false);
    };
    if outs.next().is_some()
        || !target
            .file_name()
            .is_some_and(|s| s.as_bytes().starts_with(b"generate_inline_tests-"))
    {
        return Ok(false);
    }
    let policy: Value = serde_json::from_slice(&fs::read(capsule.join("policy.json"))?)?;
    if target.as_os_str().as_bytes() != text(&policy, "target")?.as_bytes() {
        return Ok(false);
    }
    let mut random = [0u8; 16];
    File::open("/dev/urandom")?.read_exact(&mut random)?;
    let nonce = hex(&random);
    let mut log = json!({"schema":1,"pid":std::process::id(),"nonce":nonce,"target":target,"decision":"real-stock"});
    let why =
        check(capsule, &policy, argv, target, &nonce, &mut log).unwrap_or("unsupported-or-io");
    log["reason"] = json!(why);
    let hit = why == "fixture-native-fresh";
    if hit {
        log["decision"] = json!(why)
    }
    let file = capsule.join("audit").join(format!("{nonce}.json"));
    let mut out = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(file)?;
    out.write_all(&serde_json::to_vec(&log)?)?;
    Ok(hit)
}
fn main() -> io::Result<()> {
    let all: Vec<_> = std::env::args_os().collect();
    let capsule = PathBuf::from(CAPSULE);
    if try_select(&capsule, &all[1..]).unwrap_or(false) {
        return Ok(());
    }
    Err(Command::new(capsule.join("ld.stock"))
        .arg0(&all[0])
        .args(&all[1..])
        .exec())
}
