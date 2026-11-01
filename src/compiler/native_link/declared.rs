//! Reuse a successful native link when a build script identifies its native archive.
//! The real linker still discovers transitive inputs. Custom drivers must declare
//! private configuration files through the build script's rerun-if-changed list.
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io::{self, Read};
#[cfg(target_os = "macos")]
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Output};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use super::{Entry, Inputs};

pub(in crate::compiler) const DRIVER: &str = "__CARGO_OHM_DECLARED_LINKER";
pub(in crate::compiler) const WATCHED: &str = "__CARGO_OHM_DECLARED_INPUTS";

pub(super) fn command(driver: &OsStr, args: &[OsString]) -> Command {
    let mut cmd = Command::new(driver);
    cmd.args(args).env_remove(DRIVER).env_remove(WATCHED);
    cmd
}

#[derive(Default, Serialize, Deserialize)]
struct Report {
    files: BTreeSet<PathBuf>,
    missing: BTreeSet<PathBuf>,
    search: BTreeSet<PathBuf>,
}

fn read_limited(path: &Path) -> Option<Vec<u8>> {
    cargo_util::paths::read_regular_bounded(path, 16 * 1024 * 1024).ok()
}

#[cfg(target_os = "macos")]
fn parse(path: &Path, output: &Path) -> Option<Report> {
    let bytes = read_limited(path)?;
    let cwd = env::current_dir().ok()?;
    let mut items = bytes.strip_suffix(&[0])?.split(|&b| b == 0);
    // The first opcode is zero, immediately followed by the linker's identification.
    if !items.next()?.is_empty() || !items.next()?.starts_with(b"@(#)PROGRAM:ld PROJECT:ld-") {
        return None;
    }
    let mut report = Report::default();
    let mut product = false;
    for item in items {
        let (&op, value) = item.split_first()?;
        if value.is_empty() {
            return None;
        }
        let path = cwd.join(OsStr::from_bytes(value));
        match op {
            0x10 => {
                report.files.insert(path);
            }
            0x11 => {
                report.missing.insert(path);
            }
            0x40 if !product && path == output => product = true,
            _ => return None,
        }
    }
    (product && !report.files.is_empty()).then_some(report)
}

#[cfg(target_os = "linux")]
fn parse(path: &Path, output: &Path) -> Option<Report> {
    let bytes = read_limited(path)?;
    let content = std::str::from_utf8(&bytes).ok()?.replace("\\\n", " ");
    let (out, deps) = content.lines().next()?.split_once(": ")?;
    if Path::new(out) != output || deps.contains(['\\', '$', '#', ':']) {
        return None;
    }
    let files = deps
        .split_ascii_whitespace()
        .map(PathBuf::from)
        .collect::<BTreeSet<_>>();
    (!files.is_empty() && files.iter().all(|p| p.is_absolute() && p.is_file())).then_some(Report {
        files,
        ..Report::default()
    })
}

/// Ask the C driver about the same prefixes and multilib mode used for linking.
#[cfg(target_os = "linux")]
fn driver_query(driver: &OsStr, args: &[OsString]) -> Option<Command> {
    let mut query = command(driver, &[]);
    for arg in args {
        let flag = arg.to_str()?;
        if let Some(prefix) = flag.strip_prefix("-B") {
            // The driver also derives library and multilib directories from -B.
            if !Path::new(prefix).is_absolute() {
                return None;
            }
            query.arg(arg);
        } else if matches!(flag, "-m32" | "-m64" | "-mx32") {
            query.arg(arg);
        }
    }
    Some(query)
}

#[cfg(target_os = "linux")]
fn search_dirs(driver: &OsStr, args: &[OsString]) -> Option<BTreeSet<PathBuf>> {
    // Some drivers search a prefix for startup files without exposing it in
    // their library search report. Leave such links to the driver.
    let out = driver_query(driver, args)?
        .arg("-print-search-dirs")
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let text = std::str::from_utf8(&out.stdout).ok()?;
    let paths = text
        .lines()
        .find_map(|line| line.strip_prefix("libraries: ="))?;
    let mut dirs: BTreeSet<_> = env::split_paths(paths).collect();
    if args
        .iter()
        .filter_map(|arg| arg.to_str()?.strip_prefix("-B"))
        .any(|prefix| !dirs.contains(Path::new(prefix)))
    {
        return None;
    }
    dirs.extend(
        [
            "/lib",
            "/lib64",
            "/usr/lib",
            "/usr/lib64",
            "/usr/local/lib",
            "/usr/local/lib64",
            "/lib/x86_64-linux-gnu",
            "/usr/lib/x86_64-linux-gnu",
            "/usr/local/lib/x86_64-linux-gnu",
        ]
        .map(PathBuf::from),
    );
    if let Some(extra) = env::var_os("LIBRARY_PATH") {
        dirs.extend(env::split_paths(&extra));
    }
    dirs.iter().all(|p| p.is_absolute()).then_some(dirs)
}

/// The driver supplies startup objects such as crti.o outside the original
/// argv. Its dependency file records the old choice even after a new one wins.
#[cfg(target_os = "linux")]
fn driver_object_covered(driver: &OsStr, args: &[OsString], path: &Path) -> Option<()> {
    if path.extension() != Some(OsStr::new("o")) || args.iter().any(|arg| Path::new(arg) == path) {
        return Some(());
    }
    let name = path.file_name()?.to_str()?;
    let out = driver_query(driver, args)?
        .arg(format!("-print-file-name={name}"))
        .output()
        .ok()?;
    let selected = std::str::from_utf8(&out.stdout).ok()?.strip_suffix('\n')?;
    (out.status.success() && Path::new(selected) == path).then_some(())
}

/// A driver prefix can also supply specs and executable plugins, whose own
/// inputs aren't reported by ld. Only keep prefixes containing tracked tools,
/// library candidates and object files.
#[cfg(target_os = "linux")]
fn gnu_prefix_covered(inputs: &mut Inputs, dir: &Path, filenames: &BTreeSet<String>) -> Option<()> {
    for (index, entry) in fs::read_dir(dir).ok()?.enumerate() {
        if index == super::MAX_DRIVER_PREFIX_ENTRIES {
            return None;
        }
        let path = entry.ok()?.path();
        let name = path.file_name()?.to_str()?;
        let tool = matches!(
            name,
            "ld" | "ld.bfd"
                | "ld.lld"
                | "ld.gold"
                | "ld64.lld"
                | "lld-link"
                | "wasm-ld"
                | "collect2"
        );
        if name == "liblto_plugin.so"
            || (!tool && !filenames.contains(name) && !name.ends_with(".o"))
        {
            return None;
        }
        observe(inputs, path)?;
    }
    inputs.directories.insert(dir.to_owned());
    Some(())
}

fn observe(inputs: &mut Inputs, path: PathBuf) -> Option<()> {
    match fs::metadata(&path) {
        Ok(meta) if meta.is_file() => {
            inputs.files.insert(path);
        }
        Err(err) if super::missing(&err) => {
            inputs.missing.insert(path);
        }
        _ => return None,
    }
    Some(())
}

fn regular_archive(path: &Path) -> bool {
    let mut magic = [0; 8];
    fs::File::open(path)
        .and_then(|mut f| f.read_exact(&mut magic))
        .is_ok()
        && &magic == b"!<arch>\n"
}

fn library_filename(path: &Path) -> Option<&str> {
    let name = path.file_name()?.to_str()?;
    (name.starts_with("lib")
        && (name.ends_with(".a")
            || name.ends_with(".so")
            || name.contains(".so.")
            || name.ends_with(".dylib")
            || name.ends_with(".tbd")))
    .then_some(name)
}

/// GNU dependency files omit failed lookups inside scripts. Admit a library
/// group only when each operand was opened by its absolute name or its possible
/// providers were already part of the driver's pre-link snapshot.
#[cfg(target_os = "linux")]
fn gnu_script_covered(
    mut script: &str,
    files: &BTreeSet<PathBuf>,
    filenames: &BTreeSet<String>,
    parent_is_searched: bool,
) -> Option<()> {
    while let Some(comment) = script.trim_start().strip_prefix("/*") {
        script = comment.split_once("*/")?.1;
    }
    let script = script.replace('(', " ( ").replace(')', " ) ");
    let mut words = script.split_ascii_whitespace();
    let mut command = words.next()?;
    if command == "OUTPUT_FORMAT" {
        if !words.by_ref().take(3).eq(["(", "elf64-x86-64", ")"]) {
            return None;
        }
        command = words.next()?;
    }
    if !matches!(command, "GROUP" | "INPUT") || words.next()? != "(" {
        return None;
    }
    let mut depth = 1;
    while let Some(word) = words.next() {
        match word {
            ")" => {
                depth -= 1;
                if depth == 0 {
                    return words.next().is_none().then_some(());
                }
            }
            "AS_NEEDED" if words.next()? == "(" => depth += 1,
            word if Path::new(word).is_absolute() && files.contains(Path::new(word)) => {}
            word if parent_is_searched && filenames.contains(word) => {}
            word if parent_is_searched && word.starts_with("-l") => {
                let name = &word[2..];
                if !filenames.contains(&format!("lib{name}.so"))
                    || !filenames.contains(&format!("lib{name}.a"))
                {
                    return None;
                }
            }
            _ => return None,
        }
    }
    None
}

/// Reject thin archives and implicit scripts whose search cannot be replayed.
#[cfg(target_os = "linux")]
fn gnu_input_covered(
    path: &Path,
    report: &Report,
    roots: &BTreeSet<PathBuf>,
    filenames: &BTreeSet<String>,
) -> Option<()> {
    use std::io::Seek;

    let target = path.canonicalize().ok()?;
    let mut file = cargo_util::paths::open_regular(&target).ok()?;
    let mut magic = [0; 8];
    file.read_exact(&mut magic).ok()?;
    if magic.starts_with(b"\x7fELF") || &magic == b"!<arch>\n" {
        return Some(());
    }
    let mut script = String::new();
    file.rewind().ok()?;
    file.take(8193).read_to_string(&mut script).ok()?;
    if script.len() > 8192 {
        return None;
    }
    // Linkers may use the resolved script's directory for a relative operand.
    let parent_is_searched = roots.contains(path.parent()?) && roots.contains(target.parent()?);
    gnu_script_covered(&script, &report.files, filenames, parent_is_searched)
}

fn tool_candidates(inputs: &mut Inputs, dir: &Path) -> Option<()> {
    for name in ["ld", "ld.bfd", "ld.lld", "ld.gold", "collect2"] {
        observe(inputs, dir.join(name))?;
    }
    Some(())
}

fn action(
    driver: &OsStr,
    args: &[OsString],
    output: &Path,
    temp: &Path,
    watched: &BTreeSet<PathBuf>,
    report: &Report,
) -> Option<Inputs> {
    let mut inputs = Inputs::default();
    let cwd = env::current_dir().ok()?;
    inputs
        .action
        .extend(["declared native link v1".into(), cwd.as_os_str().to_owned()]);
    inputs
        .files
        .insert(cargo_util::paths::resolve_executable(Path::new(driver)).ok()?);
    inputs.files.extend(watched.iter().cloned());
    let environment: BTreeMap<_, _> = env::vars_os().collect();
    for (key, val) in environment {
        if key != DRIVER && key != WATCHED {
            inputs.action.extend([key, val]);
        }
    }
    let symbols = temp.join("symbols.o");
    let raw = temp.join("raw-dylibs");
    let mut roots = report.search.clone();
    let mut tool_roots = BTreeSet::new();
    let cc = cargo_util::paths::resolve_executable(Path::new("cc")).ok()?;
    inputs.files.insert(cc);
    #[cfg(target_os = "macos")]
    if let Some(sdk) = env::var_os("SDKROOT") {
        let sdk = PathBuf::from(sdk);
        // The SDK is under Xcode's selected Developer platform. Track the actual
        // tool binaries as well as the executable named in Cargo's linker setting.
        if let Some(developer) = sdk.ancestors().find(|p| p.ends_with("Contents/Developer")) {
            let tools = developer.join("Toolchains/XcodeDefault.xctoolchain/usr");
            for name in ["bin/clang", "bin/ld", "lib/libLTO.dylib"] {
                inputs.files.insert(tools.join(name));
            }
        } else {
            return None;
        }
    } else {
        return None;
    }
    let mut names = BTreeSet::new();
    let mut i = 0;
    while i < args.len() {
        let arg = args[i].to_str()?;
        i += 1;
        if Path::new(arg) == symbols {
            inputs.action.push("rustc-symbols".into());
            inputs
                .transient
                .insert("rustc-symbols".into(), symbols.clone());
        } else if arg == "-L" || arg.starts_with("-L") {
            let root = if arg == "-L" {
                let p = args.get(i)?;
                i += 1;
                PathBuf::from(p)
            } else {
                PathBuf::from(&arg[2..])
            };
            inputs.action.push("-L".into());
            if root == raw {
                match fs::read_dir(&raw) {
                    Ok(mut entries) => {
                        if entries.next().is_some() {
                            return None;
                        }
                    }
                    Err(e) if !super::missing(&e) => return None,
                    _ => {}
                }
                inputs.action.push("rustc-empty-raw-dylibs".into());
            } else {
                if !root.is_absolute() {
                    return None;
                }
                inputs.action.push(root.as_os_str().to_owned());
                roots.insert(root);
            }
        } else {
            if arg.contains(temp.to_str()?) || arg.starts_with('@') {
                return None;
            }
            inputs.action.push(arg.into());
            if let Some(name) = arg.strip_prefix("-l") {
                if name.is_empty()
                    || !name
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b))
                {
                    return None;
                }
                names.insert(name.to_owned());
            } else if let Some(prefix) = arg.strip_prefix("-B") {
                let p = Path::new(prefix);
                if !p.is_absolute() {
                    return None;
                }
                tool_roots.insert(p.to_owned());
            } else if (cfg!(target_os = "linux")
                && (arg.starts_with("--sysroot") || arg.starts_with("-isysroot")))
                || arg.starts_with("-F")
                || arg == "-framework"
                || arg == "-Xlinker"
                || arg.starts_with("-T")
            {
                return None;
            } else if let Some(option) = arg.strip_prefix("-Wl,") {
                if !matches!(
                    option,
                    "--as-needed"
                        | "-Bstatic"
                        | "-Bdynamic"
                        | "--eh-frame-hdr"
                        | "-z,noexecstack"
                        | "--gc-sections"
                        | "-z,relro,-z,now"
                        | "-dead_strip"
                ) {
                    return None;
                }
            } else if Path::new(arg).is_absolute() && Path::new(arg) != output {
                let p = Path::new(arg);
                if !p.is_file() {
                    return None;
                }
                inputs.files.insert(p.to_owned());
            }
        }
    }
    if !watched.iter().any(|p| {
        p.file_name()
            .and_then(OsStr::to_str)
            .is_some_and(|f| names.iter().any(|name| f == format!("lib{name}.a")))
    }) {
        return None;
    }
    // GNU dependency files list successful opens but omit failed searches.
    // Track every eligible name in every -L directory, including absent directories.
    let mut filenames = BTreeSet::new();
    for name in &names {
        for suffix in ["a", "so", "dylib", "tbd"] {
            filenames.insert(format!("lib{name}.{suffix}"));
        }
    }
    #[cfg(target_os = "linux")]
    {
        // GCC's libgcc_s.so group also searches for libgcc_s.so.1 and -lgcc.
        // Include these from the first link, before we have a dependency file.
        filenames.extend(["libgcc_s.so.1", "libgcc.so", "libgcc.a"].map(str::to_owned));
        for prefix in &tool_roots {
            gnu_prefix_covered(&mut inputs, prefix, &filenames)?;
        }
        roots.insert(cwd);
        for path in &report.files {
            driver_object_covered(driver, args, path)?;
            gnu_input_covered(path, report, &roots, &filenames)?;
        }
        inputs.action.push("checked GNU script inputs v2".into());
    }
    filenames.extend(
        report
            .files
            .iter()
            .filter_map(|p| library_filename(p).map(str::to_owned)),
    );
    #[cfg(target_os = "macos")]
    {
        let sdk = PathBuf::from(env::var_os("SDKROOT")?);
        for root in roots.clone() {
            roots.insert(sdk.join(root.strip_prefix("/").ok()?));
        }
    }
    for root in roots {
        for name in &filenames {
            observe(&mut inputs, root.join(name))?;
        }
    }
    for root in tool_roots {
        tool_candidates(&mut inputs, &root)?;
    }
    for path in &report.files {
        if path == &symbols {
            continue;
        }
        if path.starts_with(temp) || !path.is_absolute() {
            return None;
        }
        if path.extension().is_some_and(|s| s == "a") {
            // Thin archives and linker scripts can read other files not named
            // on the command line. Leave these to the ordinary linker.
            if !regular_archive(path) {
                return None;
            }
            #[cfg(target_os = "linux")]
            let system = ["/usr/lib", "/lib", "/lib64"]
                .iter()
                .any(|p| path.starts_with(p));
            #[cfg(target_os = "macos")]
            let system = env::var_os("SDKROOT").is_some_and(|sdk| path.starts_with(sdk));
            if !system && !watched.contains(path) {
                return None;
            }
        }
        inputs.files.insert(path.clone());
    }
    for path in &report.missing {
        if !path.starts_with(temp) {
            inputs.missing.insert(path.clone());
        }
    }
    Some(inputs)
}

fn changed_after(path: &Path, start: SystemTime) -> bool {
    let Ok(meta) = fs::metadata(path) else {
        return true;
    };
    let Ok(start) = start.duration_since(UNIX_EPOCH) else {
        return true;
    };
    (meta.ctime() as i128, meta.ctime_nsec() as i128)
        > (
            i128::from(start.as_secs()),
            i128::from(start.subsec_nanos()),
        )
}

pub(super) fn checked(
    driver: &OsStr,
    args: &[OsString],
    output: &Path,
    temp: &Path,
    objects: &Path,
) -> Option<io::Result<Output>> {
    let watched: BTreeSet<PathBuf> = serde_json::from_str(&env::var(WATCHED).ok()?).ok()?;
    if watched.is_empty()
        || watched.len() > 1024
        || !watched.iter().all(|p| p.is_absolute() && p.is_file())
    {
        return None;
    }
    let cache = Entry::open(&objects.join("declared-native")).ok()?;
    #[allow(unused_mut)]
    let mut seed = Report::default();
    #[cfg(target_os = "linux")]
    {
        // A driver can choose different directories when a prefix appears.
        seed.search = search_dirs(driver, args)?;
    }
    let closure = cache.directory.join("inputs.json");
    let prior: Option<Report> =
        read_limited(&closure).and_then(|b| serde_json::from_slice(&b).ok());
    if let Some(inputs) = prior
        .as_ref()
        .filter(|report| report.search == seed.search)
        .and_then(|r| action(driver, args, output, temp, &watched, r))
        && let Ok(snapshot) = inputs.snapshot()
        && let Some(stderr) = cache.reuse(snapshot.action, output).ok().flatten()
    {
        return Some(Ok(Output {
            status: ExitStatus::from_raw(0),
            stdout: vec![],
            stderr,
        }));
    }
    cache.invalidate().ok()?;
    let inputs = action(driver, args, output, temp, &watched, &seed)?;
    let before = inputs.snapshot().ok()?;
    let start = SystemTime::now();
    let scratch = tempfile::tempdir_in(temp).ok()?;
    let report_path = scratch.path().join("inputs");
    let mut cmd = command(driver, args);
    #[cfg(target_os = "macos")]
    cmd.args(["-Xlinker", "-dependency_info", "-Xlinker"])
        .arg(&report_path);
    #[cfg(target_os = "linux")]
    cmd.arg("-Xlinker")
        .arg(format!("--dependency-file={}", report_path.to_str()?));
    let result = cmd.output();
    if let Ok(out) = &result {
        // A third-party driver may not implement dependency reporting. Preserve
        // its ordinary command and diagnostics in that case.
        if !out.status.success() {
            let err = String::from_utf8_lossy(&out.stderr);
            if (err.contains("dependency_info") || err.contains("dependency-file"))
                && ["unknown", "unrecognized", "unsupported", "not supported"]
                    .iter()
                    .any(|word| err.contains(word))
            {
                return Some(command(driver, args).output());
            }
        }
        let stable_stderr = out.stderr.is_empty();
        #[cfg(target_os = "macos")]
        let stable_stderr = stable_stderr
            || super::apple::Prepared::declared_warnings(&out.stderr, args, &watched).is_some();
        if out.status.success()
            && out.stdout.is_empty()
            && stable_stderr
            && let Some(mut report) = parse(&report_path, output)
        {
            report.search = seed.search;
            // Compiler temporary files are authenticated using the current link's
            // symbol object. Never preserve an invocation's random temporary path.
            report.files.remove(&temp.join("symbols.o"));
            if report.files.iter().any(|p| p.starts_with(temp)) {
                return Some(result);
            }
            report.missing.retain(|p| !p.starts_with(temp));
            if inputs.snapshot().ok() == Some(before)
                && !report.files.iter().any(|p| changed_after(p, start))
                && let Some(complete) = action(driver, args, output, temp, &watched, &report)
                && let Ok(snapshot) = complete.snapshot()
                && cargo_util::paths::read_regular_bounded(output, 128 * 1024 * 1024)
                    .ok()
                    .is_some_and(|product| {
                        memchr::memmem::find(&product, temp.as_os_str().as_encoded_bytes())
                            .is_none()
                            && memchr::memmem::find(&product, b"symbols.o\0").is_none()
                    })
                && let Ok(bytes) = serde_json::to_vec(&report)
                && cargo_util::paths::write_atomic_no_follow(&closure, bytes).is_ok()
            {
                let _ = cache.publish(snapshot.action, output, &out.stderr);
            }
        }
    }
    Some(result)
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;

    #[test]
    fn gnu_scripts_cannot_introduce_unobserved_library_searches() {
        let files = [PathBuf::from("/lib/libc.so.6"), PathBuf::from("/lib/ld.so")]
            .into_iter()
            .collect();
        let names = ["libgcc_s.so.1", "libgcc.so", "libgcc.a"]
            .map(String::from)
            .into();
        let covered = |script, parent| gnu_script_covered(script, &files, &names, parent).is_some();

        assert!(covered(
            "/* GNU ld script */ GROUP(libgcc_s.so.1 -lgcc)",
            true
        ));
        assert!(covered(
            "OUTPUT_FORMAT(elf64-x86-64) GROUP(/lib/libc.so.6 AS_NEEDED(/lib/ld.so))",
            false
        ));
        assert!(!covered("GROUP(libgcc_s.so.1 -lgcc)", false));
        assert!(!covered("GROUP(/lib/libc.so.6 -lohm_private)", true));
        assert!(!covered("GROUP(/lib/missing.so)", true));
        assert!(!covered("SEARCH_DIR(/new) INPUT(-lgcc)", true));
        assert!(!covered("INPUT(-lgcc) INCLUDE unknown.ld", true));
    }

    #[cfg(all(target_arch = "x86_64", target_env = "gnu"))]
    #[test]
    fn startup_objects_follow_the_drivers_current_prefix() {
        let dir = tempfile::tempdir().unwrap();
        let high = dir.path().join("high");
        let low = dir.path().join("low");
        fs::create_dir(&high).unwrap();
        fs::create_dir(&low).unwrap();
        let args = [&high, &low].map(|p| OsString::from(format!("-B{}/", p.display())));
        let high = high.join("ohm-startup.o");
        let low = low.join("ohm-startup.o");
        let cc = OsStr::new("cc");

        fs::write(&low, b"original").unwrap();
        assert!(driver_object_covered(cc, &args, &low).is_some());
        fs::write(&high, b"replacement").unwrap();
        assert!(driver_object_covered(cc, &args, &low).is_none());
        assert!(driver_object_covered(cc, &args, &high).is_some());
    }

    #[test]
    fn a_driver_prefix_with_private_specs_cannot_publish_a_link() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("ld.bfd"), b"linker").unwrap();
        let mut inputs = Inputs::default();
        assert!(gnu_prefix_covered(&mut inputs, dir.path(), &BTreeSet::new()).is_some());
        assert!(inputs.directories.contains(dir.path()));
        let before = inputs.snapshot().unwrap();

        fs::write(dir.path().join("specs"), b"private specs").unwrap();
        assert!(gnu_prefix_covered(&mut Inputs::default(), dir.path(), &BTreeSet::new()).is_none());
        assert_ne!(before, inputs.snapshot().unwrap());
    }
}
