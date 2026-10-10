//! Test double for Cargo's process protocol; each response uses a fresh real compiler.
use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, Write};
use std::process::Command;

fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if !args.iter().any(|arg| arg == "-Zohm-check-session") {
        std::process::exit(Command::new("rustc").args(args).status().unwrap().code().unwrap_or(1));
    }
    writeln!(OpenOptions::new().create(true).append(true).open("worker-starts").unwrap(), "{}", std::process::id()).unwrap();
    let args: Vec<_> = args.into_iter().filter(|arg| {
        let arg = arg.to_string_lossy();
        !arg.starts_with("-Zohm-check-session") && !arg.starts_with("-Zohm-resident-") && arg != "-Zthreads=1"
    }).collect();
    let mut revision = 0;
    loop {
        if fs::metadata("decline").is_ok() {
            eprintln!(r#"{{"$message_type":"diagnostic","level":"error","message":"discard this provisional diagnostic"}}"#);
            eprintln!(r#"{{"$message_type":"ohm-check-session","protocol":1,"kind":"unsupported","revision":{revision},"errors":true,"retained":false}}"#);
            return;
        }
        let output = Command::new("rustc").args(&args).output().unwrap();
        io::stderr().write_all(&output.stderr).unwrap();
        let kind = if revision == 0 { "ready" } else { "checked" };
        let errors = !output.status.success();
        eprintln!(r#"{{"$message_type":"ohm-check-session","protocol":1,"kind":"{kind}","revision":{revision},"errors":{errors},"retained":true}}"#);
        let mut request = String::new();
        if io::stdin().lock().read_line(&mut request).unwrap() == 0 { return; }
        revision += 1;
    }
}
