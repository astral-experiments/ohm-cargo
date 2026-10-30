use std::collections::hash_map::DefaultHasher;
use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::hash::Hasher;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut argv = env::args_os().skip(1);
    let rustc = argv.next().ok_or("expected rustc")?;
    let args: Vec<OsString> = argv.collect();
    let name = args
        .windows(2)
        .find(|arg| arg[0] == "--crate-name")
        .map(|arg| &arg[1]);
    let parser_unit = name.is_some_and(|n| n == "ruff_python_ast" || n == "ruff_python_parser");
    let guarded = args
        .iter()
        .any(|arg| arg.to_string_lossy().contains("ohm-check-relink-inputs"));
    if !parser_unit
        || !guarded
        || env::var_os("OHM_REPLAY_ROLE").as_deref() != Some(OsStr::new("Q"))
    {
        return Err(Command::new(rustc).args(args).exec().into());
    }

    let manifest_dir =
        PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").ok_or("missing manifest path")?);
    let head = manifest_dir
        .ancestors()
        .find_map(|dir| fs::read(dir.join(".git/HEAD")).ok())
        .ok_or("expected the private Ruff checkout")?;
    let mut hasher = DefaultHasher::new();
    hasher.write(head.trim_ascii_end());
    let script =
        PathBuf::from(env::var_os("OHM_REPLAY_DIRECTORY").ok_or("missing replay directory")?)
            .join("tables.py");
    let error = Command::new("python3")
        .arg("-IB")
        .arg(script)
        .arg(format!("{:016x}", hasher.finish()))
        .arg(name.unwrap())
        .arg(rustc)
        .args(args)
        .exec();
    Err(error.into())
}
