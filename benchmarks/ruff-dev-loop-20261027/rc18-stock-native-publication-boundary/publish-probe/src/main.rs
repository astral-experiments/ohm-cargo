//! Private post-GCC publication experiment. A held, independently authenticated image is precondition.
mod publish;

use std::env;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io;
use std::os::fd::FromRawFd;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::process::CommandExt;
use std::process::{Command, ExitCode};

fn main() -> io::Result<ExitCode> {
    let stock=env::var_os("OHM_PROBE_WILD").expect("exact private stock linker");
    let argv: Vec<OsString>=env::args_os().skip(1).collect();
    let mut receipt=Vec::new();
    for arg in &argv { receipt.extend_from_slice(arg.as_os_str().as_bytes());receipt.push(0); }
    fs::write(env::var_os("OHM_PROBE_ARGV").unwrap(),receipt)?;
    let mut action="uncertified-inputs";
    if let Some(raw)=env::var_os("OHM_TEST_CERTIFIED_IMAGE_FD") {
        // The disposable supervisor opens exactly this FD, computes its own independent input
        // approval, and keeps the sealed image alive across GCC and collect2. Ambient config must
        // never grant this authority in a production design.
        let image=unsafe {File::from_raw_fd(raw.to_str().unwrap().parse::<i32>().unwrap())};
        if let Some(jobserver)=unsafe {jobserver::Client::from_env()} {
            let mut tokens=Vec::new();
            while let Some(token)=jobserver.try_acquire()? {
                tokens.push(token);
                if tokens.len()==15 {break}
            }
            let n=tokens.len()+1;
            fs::write(env::var_os("OHM_PROBE_WIDTH").unwrap(),n.to_string())?;
            action=publish::replay(&argv,n,image).unwrap_or("io-error");
            drop(tokens);
        } else {action="unsupported-jobserver"}
    }
    fs::write(env::var_os("OHM_PROBE_ACTION").unwrap(),action)?;
    if action=="hit" {return Ok(ExitCode::SUCCESS)}
    // On refusal, the stock child sees the original driver arguments and the returned jobserver.
    Err(Command::new(stock).args(argv).exec())
}
