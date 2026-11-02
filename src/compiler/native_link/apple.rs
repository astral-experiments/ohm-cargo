//! Resolve the narrow, native arm64 Apple clang executable action produced by rustc.
//! The ordinary linker owns all other actions and side effects.
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::os::unix::ffi::OsStrExt;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

use object::read::archive::ArchiveFile;
use object::read::macho::MachOFile64;
use object::{Object, ObjectKind, macho};

use super::Inputs;

pub(super) struct Prepared {
    pub(super) inputs: Inputs,
    cwd: PathBuf,
    output: PathBuf,
    symbols: PathBuf,
    explicit: BTreeSet<PathBuf>,
    roots: BTreeSet<PathBuf>,
    sdk: PathBuf,
    libraries: BTreeSet<String>,
    reachable: BTreeSet<String>,
    sdk_stubs: BTreeSet<PathBuf>,
    frameworks: BTreeSet<String>,
    driver: PathBuf,
    clang: PathBuf,
    argv: Vec<OsString>,
    env: BTreeMap<OsString, OsString>,
    release: String,
    expected: Vec<String>,
    ld: PathBuf,
    lto: PathBuf,
}

fn clean(path: &Path) -> bool {
    path.is_absolute() && !path.components().any(|p| matches!(p, Component::ParentDir))
}

fn extension(path: &Path) -> bool {
    path.extension().and_then(OsStr::to_str).is_some_and(|ext| {
        ["tbd", "dylib", "so", "a"]
            .iter()
            .any(|expected| ext.eq_ignore_ascii_case(expected))
    })
}

fn environment(command: &Command) -> Option<BTreeMap<OsString, OsString>> {
    let mut env: BTreeMap<_, _> = env::vars_os().collect();
    for (key, value) in command.get_envs() {
        if let Some(value) = value {
            env.insert(key.to_owned(), value.to_owned());
        } else {
            env.remove(key);
        }
    }
    for key in env.keys() {
        let name = key.to_str()?;
        // These tool-specific families can select an unmodelled config, tool,
        // library, logging destination, response file or post-link operation.
        // Preserve and bind unrelated shell/application variables normally.
        if name == "DYLD_FALLBACK_LIBRARY_PATH" {
            continue;
        }
        if [
            "DYLD_",
            "LD_",
            "LD64_",
            "CCC_",
            "CLANG_",
            "LLVM_",
            "LTO_",
            "TAPI_",
            "SWIFT_",
            "RC_",
            "QA_OVERRIDE",
            "XCRUN_",
            "_XCRUN_",
            "CC_",
            "COMPILER_RT_",
            "CODESIGN_",
            "TOOLCHAIN_",
            "SDK_",
            "XCODE_",
        ]
        .iter()
        .any(|p| name.starts_with(p))
            || matches!(
                name,
                "LIBRARY_PATH"
                    | "COMPILER_PATH"
                    | "GCC_EXEC_PREFIX"
                    | "LPATH"
                    | "TOOLCHAINS"
                    | "DEVELOPER_DIR"
                    | "CPATH"
                    | "CPLUS_INCLUDE_PATH"
                    | "OBJC_INCLUDE_PATH"
                    | "C_INCLUDE_PATH"
                    | "LD_LIBRARY_PATH"
            )
        {
            return None;
        }
    }
    Some(env)
}

fn xcrun(args: &[&str], env: &BTreeMap<OsString, OsString>) -> Option<PathBuf> {
    let result = Command::new("/usr/bin/xcrun")
        .env_clear()
        .envs(env)
        .args(args)
        .output()
        .ok()?;
    if !result.status.success() || !result.stderr.is_empty() {
        return None;
    }
    let name = result.stdout.strip_suffix(b"\n")?;
    if name.contains(&b'\n') {
        return None;
    }
    let path = PathBuf::from(OsStr::from_bytes(name));
    clean(&path).then_some(path)
}

fn apple_tool(path: &Path, identifier: &str) -> bool {
    let req = format!("-R=anchor apple and identifier \"{identifier}\"");
    Command::new("/usr/bin/codesign")
        .arg("--verify")
        .arg(req)
        .arg(path)
        .output()
        .is_ok_and(|result| result.status.success())
}

fn quoted_job(line: &str) -> Option<Vec<String>> {
    // clang -### prints each argument double quoted. Unknown quoting or an extra
    // line is a different driver dialect; never invoke a shell to decode this.
    let line = line.trim_start().strip_prefix('"')?.strip_suffix('"')?;
    let args: Vec<_> = line.split("\" \"").collect();
    args.iter()
        .all(|arg| !arg.is_empty() && !arg.contains(['"', '\\', '\n', '\r']))
        .then(|| args.into_iter().map(str::to_owned).collect())
}

fn numeric_version(s: &str) -> bool {
    !s.is_empty()
        && s.split('.')
            .all(|v| !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit()))
}

fn parse_macos_version(value: &str) -> Option<u32> {
    if !numeric_version(value) {
        return None;
    }
    let mut parts = value.split('.');
    let major: u16 = parts.next()?.parse().ok()?;
    let minor: u8 = parts.next().unwrap_or("0").parse().ok()?;
    let patch: u8 = parts.next().unwrap_or("0").parse().ok()?;
    parts
        .next()
        .is_none()
        .then(|| (u32::from(major) << 16) | (u32::from(minor) << 8) | u32::from(patch))
}

fn safe_library(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b))
}

fn darwin_release() -> Option<String> {
    let mut uts = std::mem::MaybeUninit::<libc::utsname>::uninit();
    // uname initializes the fixed-size, NUL-terminated uname fields on success.
    if unsafe { libc::uname(uts.as_mut_ptr()) } != 0 {
        return None;
    }
    let uts = unsafe { uts.assume_init() };
    Some(
        unsafe { std::ffi::CStr::from_ptr(uts.release.as_ptr()) }
            .to_str()
            .ok()?
            .into(),
    )
}

const SDK_LIBRARY_DIRS: [&str; 4] = [
    "usr/lib",
    "usr/lib/system",
    "usr/lib/swift",
    "usr/local/lib",
];

fn search_roots(sdk: &Path, paths: Vec<PathBuf>) -> Option<BTreeSet<PathBuf>> {
    let mut roots = BTreeSet::new();
    for path in paths {
        // ld searches the SDK-prefixed absolute -L first and may omit
        // that directory from its report entirely while it is absent.
        roots.insert(sdk.join(path.strip_prefix("/").ok()?));
        roots.insert(path);
    }
    roots.extend(SDK_LIBRARY_DIRS.map(|directory| sdk.join(directory)));
    Some(roots)
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum Lookup {
    Library(String),
    /// Ordered framework names from the enclosing umbrella to its child.
    Framework(Vec<String>),
    /// Observe a referenced install name even when ld need not load it.
    PotentialFramework(Vec<String>),
}

fn framework_name(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
}

fn framework_chain(relative: &Path) -> Option<Vec<String>> {
    let parts: Vec<_> = relative
        .strip_prefix("System/Library/Frameworks")
        .ok()?
        .iter()
        .map(|p| p.to_str())
        .collect::<Option<_>>()?;
    let mut rest = parts.as_slice();
    let mut chain = Vec::new();
    loop {
        let [bundle, "Versions", version, tail @ ..] = rest else {
            return None;
        };
        let name = bundle.strip_suffix(".framework")?;
        if !framework_name(name) || !framework_name(version) {
            return None;
        }
        chain.push(name.to_owned());
        match tail {
            [binary] if *binary == name => return Some(chain),
            ["Frameworks", sub @ ..] if chain.len() == 1 => rest = sub,
            _ => return None,
        }
    }
}

/// Only accept the plain TAPI v4 spelling used by native SDK system stubs.
/// Every install name and re-export must remain inside a planned SDK search
/// directory. Other formats or dependencies go through the ordinary linker.
fn closed_sdk_stub(path: &Path, sdk: &Path, allow_frameworks: bool) -> Option<BTreeSet<Lookup>> {
    let mut names = BTreeSet::new();
    let text = fs::read_to_string(path).ok()?;
    if !text.starts_with("--- !tapi-tbd\ntbd-version:") || !text.is_ascii() {
        return None;
    }
    // No YAML aliases, escapes, tags other than the document header, flow
    // maps or folded scalars. An unsupported representation is a cache miss.
    let mut potential = BTreeSet::new();
    let mut libraries = false;
    for line in text.lines() {
        let line = line.trim();
        if line == "--- !tapi-tbd" && !libraries {
            continue;
        }
        if line
            .bytes()
            .any(|b| b < 32 || b"&*!#\\\"|>{}@?%".contains(&b))
        {
            return None;
        }
        let mut start = line;
        if !libraries {
            if let Some((key, value)) = line.trim_start_matches("- ").split_once(':') {
                match key {
                    "libraries" => {
                        start = value.trim().strip_prefix('[')?;
                        libraries = true;
                    }
                    "install-name" => {
                        names.insert(sdk_install_name(value.trim())?);
                    }
                    "tbd-version" if value.trim() == "4" => {}
                    "reexported-libraries" if value.trim().is_empty() => {}
                    "umbrella" if allow_frameworks => {
                        let parent = value.trim();
                        if !framework_name(parent) {
                            return None;
                        }
                        potential.insert(Lookup::PotentialFramework(vec![parent.to_owned()]));
                    }
                    "targets"
                    | "current-version"
                    | "compatibility-version"
                    | "exports"
                    | "reexports"
                    | "symbols"
                    | "allowable-clients"
                    | "clients"
                    | "objc-ivars"
                    | "objc-eh-types"
                    | "objc-classes"
                    | "weak-symbols"
                    | "parent-umbrella"
                    | "umbrella" => {}
                    _ => return None,
                }
            }
        }
        if libraries {
            if let Some(end) = start.strip_suffix(']') {
                start = end;
                libraries = false;
            }
            for name in start.split(',').map(str::trim).filter(|s| !s.is_empty()) {
                names.insert(sdk_install_name(name)?);
            }
        }
        for word in line
            .split(|c: char| c.is_ascii_whitespace() || "[],".contains(c))
            .filter(|s| s.contains('/'))
        {
            if let Some(directive) = word
                .strip_prefix("'$ld$previous$")
                .and_then(|v| v.strip_suffix("'"))
            {
                // A symbol can name a previous install location. Bind candidates
                // for that location, but decline if ld actually reads one unless
                // it is also a separately validated install name or re-export.
                let (install, fields) = directive.split_once('$')?;
                if fields.contains('/') || !allow_frameworks {
                    return None;
                }
                let path = Path::new(install).strip_prefix("/").ok()?;
                potential.insert(Lookup::PotentialFramework(framework_chain(path)?));
            } else {
                names.insert(sdk_install_name(word)?);
            }
        }
    }
    if libraries {
        return None;
    }
    let mut stems = potential;
    for relative in names {
        if !sdk.join(relative).with_extension("tbd").is_file() {
            return None;
        }
        if relative.extension() == Some(OsStr::new("dylib")) {
            stems.insert(Lookup::Library(
                relative.file_stem()?.to_str()?.to_ascii_lowercase(),
            ));
        } else if allow_frameworks {
            stems.insert(Lookup::Framework(framework_chain(relative)?));
        } else {
            return None;
        }
    }
    Some(stems)
}

fn sdk_install_name(value: &str) -> Option<&Path> {
    let path = Path::new(value.strip_prefix('\'')?.strip_suffix('\'')?);
    let relative = path.strip_prefix("/").ok()?;
    if framework_chain(relative).is_some() {
        return Some(relative);
    }
    let name = path.file_name()?.to_str()?;
    if !safe_library(name)
        || !name.starts_with("lib")
        || path.extension()? != "dylib"
        || !SDK_LIBRARY_DIRS
            .iter()
            .any(|dir| relative.parent() == Some(Path::new(dir)))
    {
        return None;
    }
    Some(relative)
}

fn namespace(
    inputs: &mut Inputs,
    root: &Path,
    entries: &mut BTreeMap<String, Vec<PathBuf>>,
) -> Option<()> {
    match fs::metadata(root) {
        Ok(meta) if meta.is_dir() => {
            inputs.directories.insert(root.to_owned());
            for entry in fs::read_dir(root).ok()? {
                let path = entry.ok()?.path();
                // A case-insensitive volume may fold a non-ASCII extension
                // into a requested spelling. Refuse unmodelled collation.
                if path
                    .extension()
                    .is_some_and(|e| !e.as_encoded_bytes().is_ascii())
                {
                    return None;
                }
                if !extension(&path) {
                    continue;
                }
                let stem = path.file_stem()?.to_str()?;
                if !stem.is_ascii() {
                    return None;
                } // Avoid unmodelled filesystem case folding.
                entries
                    .entry(stem.to_ascii_lowercase())
                    .or_default()
                    .push(path);
            }
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            inputs.missing.insert(root.to_owned());
        }
        _ => return None,
    }
    Some(())
}

/// Observe only binary/stub lookup locations inside conventional framework
/// bundles. Refuse a non-SDK binary or stub instead of trying to resolve it.
fn framework_candidates(inputs: &mut Inputs, sdk: &Path, chain: &[String]) -> Option<Vec<PathBuf>> {
    fn directory(inputs: &mut Inputs, p: &Path) -> Option<bool> {
        match fs::metadata(p) {
            Ok(m) if m.is_dir() => {
                inputs.directories.insert(p.to_owned());
                Some(true)
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                inputs.missing.insert(p.to_owned());
                Some(false)
            }
            _ => None,
        }
    }
    let mut search = Vec::new();
    for root in [
        "Library/Frameworks",
        "Network/Library/Frameworks",
        "System/Library/Frameworks",
    ] {
        search.push(sdk.join(root));
        search.push(Path::new("/").join(root));
    }
    let mut found = Vec::new();
    for (i, name) in chain.iter().enumerate() {
        let mut children = BTreeSet::new();
        for root in search {
            let bundle = root.join(format!("{name}.framework"));
            if !directory(inputs, &bundle)? {
                continue;
            }
            let versions = bundle.join("Versions");
            let mut variants = vec![bundle.clone()];
            if directory(inputs, &versions)? {
                for entry in fs::read_dir(&versions).ok()? {
                    let p = entry.ok()?.path();
                    if !framework_name(p.file_name()?.to_str()?) || !directory(inputs, &p)? {
                        return None;
                    }
                    variants.push(p);
                }
            }
            for variant in variants {
                if i + 1 < chain.len() {
                    children.insert(variant.join("Frameworks"));
                    continue;
                }
                let binary = variant.join(name);
                for p in [binary.with_extension("tbd"), binary] {
                    match fs::metadata(&p) {
                        Ok(m)
                            if m.is_file()
                                && p.starts_with(sdk)
                                && p.extension() == Some(OsStr::new("tbd")) =>
                        {
                            found.push(p);
                        }
                        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                            inputs.missing.insert(p);
                        }
                        _ => return None,
                    }
                }
            }
        }
        search = children.into_iter().collect();
    }
    Some(found)
}

/// All by-name native reads descend from an explicit -l, or from a selected
/// plain SDK stub's install name/reexports. Look up every candidate for each
/// such name in every root, including shadows and dangling symlinks.
/// Account for each requested name and its SDK reexports before invoking ld.
/// The real link must independently confirm that every selected stub was checked.
fn library_inputs(
    inputs: &mut Inputs,
    roots: &BTreeSet<PathBuf>,
    libraries: &BTreeSet<String>,
    frameworks: &BTreeSet<String>,
    sdk: &Path,
) -> Option<(BTreeSet<String>, BTreeSet<PathBuf>)> {
    let mut namespace_by_name = BTreeMap::new();
    for root in roots {
        namespace(inputs, root, &mut namespace_by_name)?;
    }
    let canonical_sdk = sdk.canonicalize().ok()?;
    let mut todo: Vec<_> = libraries
        .iter()
        .map(|n| Lookup::Library(format!("lib{}", n.to_ascii_lowercase())))
        .chain(
            frameworks
                .iter()
                .map(|n| Lookup::Framework(vec![n.clone()])),
        )
        .collect();
    let mut seen = BTreeSet::new();
    let mut reachable = BTreeSet::new();
    let mut stubs = BTreeSet::new();
    while let Some(lookup) = todo.pop() {
        if !seen.insert(lookup.clone()) {
            continue;
        }
        let inspect_stubs = !matches!(lookup, Lookup::PotentialFramework(_));
        let paths = match lookup {
            Lookup::Library(name) => {
                reachable.insert(name.clone());
                namespace_by_name.remove(&name).unwrap_or_default()
            }
            Lookup::Framework(chain) | Lookup::PotentialFramework(chain) => {
                // ld can find an indirect child first as a top-level framework
                // with that name, and otherwise at its declared nested install path.
                if chain.len() > 1 {
                    let flat = vec![chain.last()?.clone()];
                    todo.push(if inspect_stubs {
                        Lookup::Framework(flat)
                    } else {
                        Lookup::PotentialFramework(flat)
                    });
                }
                framework_candidates(inputs, sdk, &chain)?
            }
        };
        for p in paths {
            match fs::metadata(&p) {
                Ok(m) if m.is_file() => {
                    if p.extension()?.eq_ignore_ascii_case("tbd") {
                        let file = p.canonicalize().ok()?;
                        if !p.starts_with(sdk) || !file.starts_with(&canonical_sdk) {
                            return None;
                        }
                        if inspect_stubs && stubs.insert(file) {
                            todo.extend(closed_sdk_stub(&p, sdk, !frameworks.is_empty())?);
                        }
                    }
                    inputs.files.insert(p);
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    inputs.missing.insert(p);
                }
                _ => return None,
            }
        }
    }
    Some((reachable, stubs))
}

pub(super) fn prepare(
    command: &Command,
    output: &Path,
    tmpdir: &Path,
    codegen_objects: &[&Path],
) -> Option<Prepared> {
    if !clean(output) || !clean(tmpdir) {
        return None;
    }
    let cwd = command
        .get_current_dir()
        .map(Path::to_owned)
        .or_else(|| env::current_dir().ok())?;
    let env = environment(command)?;
    let mut driver = PathBuf::from(command.get_program());
    if driver.components().count() == 1 {
        driver = env::split_paths(env.get(OsStr::new("PATH"))?)
            .map(|dir| dir.join(&driver))
            .find(|path| path.is_file())?;
    }
    // Use the platform shims, which remove dyld injection settings at exec.
    if !matches!(driver.to_str(), Some("/usr/bin/cc" | "/usr/bin/clang")) {
        return None;
    }

    let symbols = tmpdir.join("symbols.o");
    let mut required: BTreeSet<_> = codegen_objects.iter().map(|p| p.to_path_buf()).collect();
    required.insert(symbols.clone());
    if required.iter().any(|p| !clean(p)) {
        return None;
    }
    let argv: Vec<_> = command
        .get_args()
        .map(OsStr::to_str)
        .collect::<Option<_>>()?;
    let (mut body, mut roots, mut libraries, mut explicit) =
        (Vec::new(), Vec::new(), BTreeSet::new(), BTreeSet::new());
    let (mut arch, mut target, mut out, mut strip, mut defaults) =
        (false, None, false, false, false);
    let mut frameworks = BTreeSet::new();
    let mut args = argv.iter().copied();
    while let Some(arg) = args.next() {
        match arg {
            "-arch" if !arch && args.next()? == "arm64" => arch = true,
            "-o" if !out && Path::new(args.next()?) == output => out = true,
            "-L" => {
                let dir = PathBuf::from(args.next()?);
                if !clean(&dir) {
                    return None;
                }
                roots.push(dir);
            }
            "-framework" => {
                let name = args.next()?;
                if !framework_name(name) {
                    return None;
                }
                frameworks.insert(name.to_owned());
                body.push(arg);
                body.push(name);
            }
            "-Wl,-dead_strip" if !strip => strip = true,
            "-nodefaultlibs" if !defaults => defaults = true,
            _ if arg.starts_with("-mmacosx-version-min=") && target.is_none() => {
                let v = arg.split_once('=')?.1;
                if !numeric_version(v) {
                    return None;
                }
                target = Some(v);
            }
            _ if arg.starts_with("-l") && safe_library(&arg[2..]) => {
                libraries.insert(arg[2..].to_owned());
                body.push(arg);
            }
            _ => {
                let path = PathBuf::from(arg);
                if !clean(&path) || (!required.contains(&path) && path.extension()? != "rlib") {
                    return None;
                }
                explicit.insert(path);
                body.push(arg);
            }
        }
    }
    if !(arch && out && strip && defaults) || !required.is_subset(&explicit) || libraries.is_empty()
    {
        return None;
    }

    let clang = xcrun(&["--find", "clang"], &env)?;
    let ld = xcrun(&["--find", "ld"], &env)?;
    let sdk = xcrun(&["--sdk", "macosx", "--show-sdk-path"], &env)?;
    if let Some(root) = env.get(OsStr::new("SDKROOT")) {
        if Path::new(root).canonicalize().ok()? != sdk.canonicalize().ok()? {
            return None;
        }
    }
    let lto = clang.parent()?.parent()?.join("lib/libLTO.dylib");
    if ld != clang.parent()?.join("ld") || target?.split('.').next()?.parse::<u32>().ok()? < 11 {
        return None;
    }
    // Accept one known ld job only. Additional flags may read implicit files,
    // introduce observable side effects or add another post-link job.
    let mut expected = vec![
        ld.to_str()?,
        "-demangle",
        "-lto_library",
        lto.to_str()?,
        "-dynamic",
        "-arch",
        "arm64",
        "-platform_version",
        "macos",
        target?,
        "<selected-sdk-version>",
        "-syslibroot",
        sdk.to_str()?,
        "-mllvm",
        "-enable-linkonceodr-outlining",
        "-o",
        output.to_str()?,
    ]
    .into_iter()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    for root in &roots {
        expected.push(format!("-L{}", root.to_str()?));
    }
    expected.extend(body.iter().copied().map(str::to_owned));
    expected.push("-dead_strip".into());

    let mut inputs = Inputs::default();
    // This group of signed Xcode drivers must report exactly the selected
    // clang bin directory as the config search path. Probe every .cfg spelling
    // there. Extra conventional user/system configs conservatively decline.
    let home = Path::new(env.get(OsStr::new("HOME"))?);
    for config_root in [
        clang.parent()?.to_owned(),
        home.join(".config/clang"),
        PathBuf::from("/etc/clang"),
    ] {
        if !clean(&config_root) {
            return None;
        }
        match fs::metadata(&config_root) {
            Ok(m) if m.is_dir() => {
                for entry in fs::read_dir(&config_root).ok()? {
                    let path = entry.ok()?.path();
                    if path
                        .extension()
                        .is_some_and(|e| !e.as_encoded_bytes().is_ascii())
                    {
                        return None;
                    }
                    if path
                        .extension()
                        .and_then(OsStr::to_str)
                        .is_some_and(|ext| ext.eq_ignore_ascii_case("cfg"))
                    {
                        if !path.is_file() {
                            return None;
                        }
                        inputs.files.insert(path);
                    }
                }
                inputs.directories.insert(config_root);
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                inputs.missing.insert(config_root);
            }
            _ => return None,
        }
    }
    for cfg in [PathBuf::from("/etc/clang.cfg"), home.join(".clang.cfg")] {
        if fs::symlink_metadata(&cfg).err()?.kind() != std::io::ErrorKind::NotFound {
            return None;
        }
        inputs.missing.insert(cfg);
    }
    // Bind the running version of the SDK/driver defaults in addition to the
    // absolute tools selected by xcrun on every invocation.
    inputs.files.insert(PathBuf::from(
        "/System/Library/CoreServices/SystemVersion.plist",
    ));
    for path in [
        driver.as_path(),
        clang.as_path(),
        ld.as_path(),
        lto.as_path(),
        Path::new("/usr/bin/xcrun"),
        Path::new("/usr/bin/codesign"),
    ] {
        inputs.files.insert(path.to_owned());
    }
    for config in ["SDKSettings.json", "SDKSettings.plist"] {
        inputs.files.insert(sdk.join(config));
    }
    for p in &explicit {
        if p == &symbols {
            inputs.transient.insert("rustc-symbols".into(), p.clone());
        } else {
            inputs.files.insert(p.clone());
        }
    }
    let roots = search_roots(&sdk, roots)?;
    let (reachable, sdk_stubs) =
        library_inputs(&mut inputs, &roots, &libraries, &frameworks, &sdk)?;

    let release = darwin_release()?;
    inputs.action.extend([
        "apple-clang-macos-framework-v6".into(),
        release.as_str().into(),
        cwd.as_os_str().to_owned(),
        output.as_os_str().to_owned(),
    ]);
    for vector in [argv.clone(), expected.iter().map(String::as_str).collect()] {
        inputs.action.push(vector.len().to_string().into());
        for arg in vector {
            if Path::new(arg) == symbols {
                inputs.action.push("rustc-symbols".into());
            } else {
                inputs.action.push(arg.into());
            }
        }
    }
    // Only the digest is persisted. Preserve field boundaries in the shared encoder.
    for (name, value) in &env {
        inputs.action.extend([name.clone(), value.clone()]);
    }
    Some(Prepared {
        inputs,
        cwd,
        output: output.to_owned(),
        symbols,
        explicit,
        roots,
        sdk,
        libraries,
        reachable,
        sdk_stubs,
        frameworks,
        driver,
        clang,
        release,
        argv: argv.into_iter().map(OsString::from).collect(),
        env,
        expected,
        ld,
        lto,
    })
}

fn relocatable(bytes: &[u8], symbols: bool) -> Option<()> {
    use object::ObjectSection;
    let file = MachOFile64::<object::Endianness>::parse(bytes).ok()?;
    if file.kind() != ObjectKind::Relocatable
        || file.architecture() != object::Architecture::Aarch64
    {
        return None;
    }
    let mut commands = file.macho_load_commands().ok()?;
    while let Some(load) = commands.next().ok()? {
        match load.cmd() {
            macho::LC_SEGMENT_64
            | macho::LC_BUILD_VERSION
            | macho::LC_VERSION_MIN_MACOSX
            | macho::LC_SYMTAB
            | macho::LC_DYSYMTAB
            | macho::LC_LINKER_OPTIMIZATION_HINT => {}
            _ => return None, // Includes LC_LINKER_OPTION and its implicit libraries/frameworks.
        }
    }
    // Native Rust rlib members have ordinary machine code and may also contain
    // __LLVM,__bitcode for rustc LTO. The admitted ld action uses the native
    // sections and discards embedded bitcode. Raw LLVM bitcode is rejected by
    // the Mach-O parser above. Never accept a bitcode-bundle link.
    for section in file.sections() {
        let name = section.name().ok()?;
        let segment = section.segment_name().ok()?;
        if matches!(name, "__bundle" | "__clangast") || (symbols && segment == Some("__DWARF")) {
            return None;
        }
    }
    if symbols
        && file
            .macho_symbol_table()
            .iter()
            .any(|n| n.n_type & macho::N_STAB != 0)
    {
        return None;
    }
    Some(())
}

fn supported_input(path: &Path, symbols: &Path) -> Option<()> {
    let bytes = fs::read(path).ok()?;
    match path.extension()?.to_str()? {
        "rlib" | "a" => {
            let archive = ArchiveFile::parse(bytes.as_slice()).ok()?;
            if archive.is_thin() {
                return None;
            }
            for member in archive.members() {
                let member = member.ok()?;
                relocatable(member.data(bytes.as_slice()).ok()?, false)?;
            }
        }
        "o" => relocatable(&bytes, path == symbols)?,
        _ => return None,
    }
    Some(())
}

impl Prepared {
    /// On a miss, compare the actual trusted driver expansion with the
    /// proposed action before giving the real driver any recording arguments.
    pub(super) fn authorizes_cold(&self) -> bool {
        self.check_driver().is_some()
    }

    fn check_driver(&self) -> Option<()> {
        if !apple_tool(&self.clang, "com.apple.clang")
            || !apple_tool(&self.ld, "com.apple.ld")
            || !apple_tool(&self.lto, "com.apple.libLTO")
        {
            return None;
        }
        let invoke = |args: &[&OsStr]| {
            Command::new(&self.driver)
                .args(args)
                .current_dir(&self.cwd)
                .env_clear()
                .envs(&self.env)
                .output()
                .ok()
        };
        let mut dry_args = vec![OsStr::new("-###")];
        dry_args.extend(self.argv.iter().map(OsString::as_os_str));
        let dry = invoke(&dry_args)?;
        if !dry.status.success() || !dry.stdout.is_empty() {
            return None;
        }
        let mut lines = std::str::from_utf8(&dry.stderr).ok()?.lines();
        lines.next()?.strip_prefix("Apple clang version ")?;
        let triple = lines.next()?.strip_prefix("Target: arm64-apple-darwin")?;
        if triple != self.release
            || !numeric_version(triple)
            || lines.next()? != "Thread model: posix"
            || Path::new(lines.next()?.strip_prefix("InstalledDir: ")?) != self.clang.parent()?
        {
            return None;
        }
        let mut job = quoted_job(lines.next()?)?;
        if lines.next().is_some() || job.len() != self.expected.len() {
            return None;
        }
        let sdk = Command::new("/usr/bin/xcrun")
            .env_clear()
            .envs(&self.env)
            .args(["--sdk", "macosx", "--show-sdk-version"])
            .output()
            .ok()?;
        let version = std::str::from_utf8(&sdk.stdout).ok()?.strip_suffix('\n')?;
        if !sdk.status.success()
            || !sdk.stderr.is_empty()
            || !numeric_version(version)
            || job[10] != version
        {
            return None;
        }
        job[10] = self.expected[10].clone();
        if job != self.expected {
            return None;
        }

        // Clang diagnoses every nonempty configured search dir for an explicit
        // missing config, even when the directory does not exist. Support the
        // default Xcode bin-only case. No user config is read on a qualifying link.
        let config = invoke(&[
            OsStr::new("--config=ohm-probe-absent.cfg"),
            OsStr::new("-###"),
            OsStr::new("-x"),
            OsStr::new("c"),
            OsStr::new("-"),
        ])?;
        let err = std::str::from_utf8(&config.stderr).ok()?;
        let dirs: Vec<_> = err
            .lines()
            .filter_map(|l| l.strip_prefix("clang: note: was searched for in the directory: "))
            .collect();
        let bin = self.clang.parent()?;
        if config.status.success()
            || !config.stdout.is_empty()
            || !err.lines().any(|l| {
                l == "clang: error: configuration file 'ohm-probe-absent.cfg' cannot be found"
            })
            || dirs != [bin.to_str()?]
        {
            return None;
        }
        let search = invoke(&[OsStr::new("-print-search-dirs")])?;
        if !search.status.success() || !search.stderr.is_empty() {
            return None;
        }
        let mut search_lines = std::str::from_utf8(&search.stdout).ok()?.lines();
        if Path::new(search_lines.next()?.strip_prefix("programs: =")?) != bin {
            return None;
        }
        let resource = Path::new(search_lines.next()?.strip_prefix("libraries: =")?);
        if search_lines.next().is_some()
            || resource.parent()? != bin.parent()?.join("lib/clang")
            || !numeric_version(resource.file_name()?.to_str()?)
        {
            return None;
        }
        Some(())
    }

    /// Replay only complete, stable Apple ld warnings about witnessed input.
    /// Other diagnostics still come from a real linker invocation.
    pub(super) fn cacheable_stderr(&self, stderr: &[u8]) -> bool {
        if stderr.is_empty() {
            return true;
        }
        if stderr.len() > super::MAX_STDERR || !stderr.ends_with(b"\n") {
            return false;
        }
        let Ok(text) = std::str::from_utf8(stderr) else {
            return false;
        };
        let mut archives = BTreeMap::new();
        for line in text.split_terminator('\n') {
            if self.known_warning(line, &mut archives).is_none() {
                return false;
            }
        }
        archives
            .into_iter()
            .all(|(path, members)| Self::check_warned_members(path, members).is_some())
    }

    fn known_warning<'a>(
        &self,
        line: &'a str,
        archives: &mut BTreeMap<&'a Path, BTreeMap<&'a str, u32>>,
    ) -> Option<()> {
        if line.bytes().any(|b| b < 32 || b == 127) {
            return None;
        }
        if let Some(path) = line
            .strip_prefix("ld: warning: search path '")
            .and_then(|s| s.strip_suffix("' not found"))
        {
            let p = Path::new(path);
            return (self.inputs.missing.contains(p)
                && self
                    .argv
                    .windows(2)
                    .any(|w| w[0] == "-L" && Path::new(&w[1]) == p))
            .then_some(());
        }
        let (input, versions) = line
            .strip_prefix("ld: warning: object file (")?
            .split_once(")) was built for newer 'macOS' version (")?;
        let (archive, which) = input.rsplit_once('[')?;
        let (index, member) = which.split_once("](")?;
        if index.is_empty() || !index.bytes().all(|b| b.is_ascii_digit()) || !safe_library(member) {
            return None;
        }
        let (built, target) = versions
            .strip_suffix(')')?
            .split_once(") than being linked (")?;
        let built = parse_macos_version(built)?;
        let target = parse_macos_version(target)?;
        if built <= target || target != parse_macos_version(self.expected.get(9)?)? {
            return None;
        }
        let path = Path::new(archive);
        let requested_archive = path.extension() == Some(OsStr::new("a"))
            && self.roots.contains(path.parent()?)
            && path
                .file_stem()?
                .to_str()?
                .strip_prefix("lib")
                .is_some_and(|name| self.libraries.contains(name));
        let explicit_rlib =
            path.extension() == Some(OsStr::new("rlib")) && self.explicit.contains(path);
        if !clean(path)
            || !self.inputs.files.contains(path)
            || !(requested_archive || explicit_rlib)
        {
            return None;
        }
        if archives
            .entry(path)
            .or_default()
            .insert(member, built)
            .is_some_and(|old| old != built)
        {
            return None;
        }
        Some(())
    }

    fn check_warned_members(path: &Path, expected: BTreeMap<&str, u32>) -> Option<()> {
        let bytes = fs::read(path).ok()?;
        let archive = ArchiveFile::parse(bytes.as_slice()).ok()?;
        if archive.is_thin() {
            return None;
        }
        let mut found = BTreeSet::new();
        for item in archive.members() {
            let item = item.ok()?;
            let Ok(name) = std::str::from_utf8(item.name()) else {
                continue;
            };
            let Some(&built) = expected.get(name) else {
                continue;
            };
            if !found.insert(name) {
                return None;
            }
            let object =
                MachOFile64::<object::Endianness>::parse(item.data(bytes.as_slice()).ok()?).ok()?;
            let mut commands = object.macho_load_commands().ok()?;
            let mut matching = false;
            while let Some(c) = commands.next().ok()? {
                if let Some(v) = c.build_version().ok()? {
                    if v.platform.get(object.endian()) != macho::PLATFORM_MACOS
                        || v.minos.get(object.endian()) != built
                    {
                        return None;
                    }
                    matching = true;
                }
            }
            if !matching {
                return None;
            }
        }
        (found.len() == expected.len()).then_some(())
    }

    pub(super) fn report_args(&self, path: &Path) -> Vec<OsString> {
        vec![
            "-Xlinker".into(),
            "-dependency_info".into(),
            "-Xlinker".into(),
            path.into(),
        ]
    }

    pub(super) fn reconciles(&self, report: &Path, output: &Path) -> bool {
        self.reconcile(report, output).is_some()
    }

    fn reconcile(&self, report: &Path, output: &Path) -> Option<()> {
        if output != self.output || fs::metadata(report).ok()?.len() > 16 * 1024 * 1024 {
            return None;
        }
        let data = fs::read(report).ok()?;
        let mut records = data.as_slice();
        let mut first = true;
        let mut positives = BTreeSet::new();
        let mut misses = BTreeSet::new();
        let mut found_output = false;
        while !records.is_empty() {
            let (&op, tail) = records.split_first()?;
            let end = tail.iter().position(|&b| b == 0)?;
            let value = tail.get(..end)?;
            records = tail.get(end + 1..)?;
            if value.is_empty() {
                return None;
            }
            if first {
                first = false;
                let version = std::str::from_utf8(value)
                    .ok()?
                    .strip_prefix("@(#)PROGRAM:ld PROJECT:ld-")?
                    .strip_suffix('\n')?;
                if op != 0 || !numeric_version(version) {
                    return None;
                }
                continue;
            }
            let path = self.cwd.join(OsStr::from_bytes(value));
            if !clean(&path) {
                return None;
            }
            match op {
                0x10 => {
                    positives.insert(path);
                }
                0x11 => {
                    misses.insert(path);
                }
                0x40 if records.is_empty() && path == output => found_output = true,
                _ => return None,
            }
        }
        if !found_output || positives.is_empty() || !positives.is_disjoint(&misses) {
            return None;
        }

        // ld canonicalizes some positives, omits absent -L directories, and can
        // report symlink targets instead of the lexical candidate it searched.
        // The plan therefore included those lexical names before the real link.
        let canonical: BTreeSet<PathBuf> = positives
            .iter()
            .map(|p| p.canonicalize().ok())
            .collect::<Option<_>>()?;
        let mut covered: BTreeSet<PathBuf> = BTreeSet::new();
        for p in &self.explicit {
            let file = p.canonicalize().ok()?;
            if !canonical.contains(&file) {
                return None;
            }
            supported_input(p, &self.symbols)?;
            covered.insert(file);
        }
        let sdk = self.sdk.canonicalize().ok()?;
        let mut selected = BTreeSet::new();
        let mut selected_frameworks = BTreeSet::new();
        for p in &self.inputs.files {
            if !extension(p) {
                continue;
            }
            let file = p.canonicalize().ok()?;
            if !canonical.contains(&file) {
                continue;
            }
            if p.starts_with(&self.sdk) && file.starts_with(&sdk) && p.extension()? == "tbd" {
                if !self.sdk_stubs.contains(&file) {
                    return None;
                }
            } else {
                supported_input(p, &self.symbols)?;
            }
            if let Some(name) = p.file_stem()?.to_str()?.strip_prefix("lib") {
                selected.insert(name.to_owned());
            }
            if p.starts_with(&self.sdk)
                && p.components()
                    .any(|c| Path::new(c.as_os_str()).extension() == Some(OsStr::new("framework")))
            {
                selected_frameworks.insert(p.file_stem()?.to_str()?.to_owned());
            }
            covered.insert(file);
        }
        if !self.frameworks.is_subset(&selected_frameworks) {
            return None;
        }
        if canonical != covered || !self.libraries.is_subset(&selected) {
            return None;
        }
        let canonical_roots: BTreeSet<_> = self
            .roots
            .iter()
            .filter_map(|r| r.canonicalize().ok())
            .collect();
        for miss in &misses {
            let bound_framework = !self.frameworks.is_empty()
                && miss
                    .components()
                    .any(|c| Path::new(c.as_os_str()).extension() == Some(OsStr::new("framework")))
                && miss.ancestors().any(|p| self.inputs.missing.contains(p));
            if !bound_framework
                && (!extension(miss)
                    || !self
                        .reachable
                        .contains(&miss.file_stem()?.to_str()?.to_ascii_lowercase())
                    || (!self.roots.contains(miss.parent()?)
                        && !canonical_roots.contains(miss.parent()?)))
            {
                return None;
            }
            match fs::metadata(miss) {
                Err(e)
                    if matches!(
                        e.kind(),
                        std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
                    ) => {}
                _ => return None,
            }
        }
        // Refuse to normalize the anonymous symbol object if ld put its name
        // (including a debug-map N_OSO string) into the successful executable.
        let product = fs::read(output).ok()?;
        let path = self.symbols.as_os_str().as_bytes();
        if product.windows(path.len()).any(|s| s == path)
            || product
                .windows(b"symbols.o\0".len())
                .any(|s| s == b"symbols.o\0")
        {
            return None;
        }
        Some(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sdk_prefixed_search_directory_appearing_invalidates_the_action() {
        let work = tempfile::tempdir().unwrap();
        let host = work.path().join("host");
        let sdk = work.path().join("sdk");
        fs::create_dir(&host).unwrap();
        fs::create_dir(&sdk).unwrap();
        fs::write(host.join("libanswer.a"), b"old").unwrap();
        let redirected = sdk.join(host.strip_prefix("/").unwrap());
        let digest = || {
            let mut inputs = Inputs::default();
            let roots = search_roots(&sdk, vec![host.clone()]).unwrap();
            let libraries = BTreeSet::from(["answer".to_owned()]);
            library_inputs(&mut inputs, &roots, &libraries, &BTreeSet::new(), &sdk).unwrap();
            inputs.digest().unwrap()
        };
        let before = digest();
        fs::create_dir_all(&redirected).unwrap();
        fs::write(redirected.join("libanswer.a"), b"new").unwrap();
        assert_ne!(digest(), before);
    }

    #[test]
    fn sdk_stub_must_resolve_its_reexport_inside_the_covered_sdk_directories() {
        let work = tempfile::tempdir().unwrap();
        let sdk = work.path();
        fs::create_dir_all(sdk.join("usr/lib/system")).unwrap();
        fs::write(sdk.join("usr/lib/system/libchild.tbd"), b"child").unwrap();
        let stub = sdk.join("usr/lib/libroot.tbd");
        let accepts = |dep: &str| {
            fs::write(&stub,format!("--- !tapi-tbd\ntbd-version: 4\ninstall-name: '/usr/lib/libroot.dylib'\nreexported-libraries:\n  - targets: [ arm64-macos ]\n    libraries: [ {dep} ]\n...\n")).unwrap();
            closed_sdk_stub(&stub, sdk, false).is_some()
        };
        assert!(accepts("'/usr/lib/system/libchild.dylib'"));
        assert!(!accepts(
            "'/System/Library/Frameworks/Outside.framework/Outside'"
        ));
        assert!(!accepts("'/usr/lib/system/libmissing.dylib'"));
        assert!(!accepts("'@rpath/liboutside.dylib'"));
        assert!(!accepts("*other"));
    }
    #[test]
    fn sdk_candidate_set_includes_transitive_shadows_but_ignores_unrelated_files() {
        let work = tempfile::tempdir().unwrap();
        let sdk = work.path().join("sdk");
        let host = work.path().join("native");
        fs::create_dir(&host).unwrap();
        let lib = sdk.join("usr/lib");
        fs::create_dir_all(lib.join("system")).unwrap();
        fs::write(lib.join("libroot.tbd"),"--- !tapi-tbd\ntbd-version: 4\ninstall-name: '/usr/lib/libroot.dylib'\nreexported-libraries:\n  - targets: [ arm64-macos ]\n    libraries: [ '/usr/lib/system/libchild.dylib' ]\n...\n").unwrap();
        let child = lib.join("system/libchild.tbd");
        fs::write(
            &child,
            "--- !tapi-tbd\ntbd-version: 4\ninstall-name: '/usr/lib/system/libchild.dylib'\n...\n",
        )
        .unwrap();
        let unrelated = host.join("libunrelated.a");
        fs::write(&unrelated, b"A").unwrap();
        let observe = || {
            let mut inputs = Inputs::default();
            let roots = search_roots(&sdk, vec![host.clone()]).unwrap();
            let libraries = BTreeSet::from(["root".to_owned()]);
            let (names, _) =
                library_inputs(&mut inputs, &roots, &libraries, &BTreeSet::new(), &sdk).unwrap();
            assert!(names.contains("libchild") && inputs.files.contains(&child));
            assert!(!inputs.files.contains(&unrelated));
            inputs.digest().unwrap()
        };
        let prior = observe();
        fs::write(&unrelated, b"B").unwrap();
        assert_eq!(observe(), prior);
        fs::write(host.join("libchild.a"), b"shadow").unwrap();
        assert_ne!(observe(), prior);
    }
    #[test]
    fn framework_reexports_observe_changes_to_nested_and_flattened_candidates() {
        let temp = tempfile::tempdir().unwrap();
        let sdk = temp.path();
        let frameworks = sdk.join("System/Library/Frameworks");
        let outer = "OhmTestParent";
        let child = "OhmTestChild";
        let parent = format!("/System/Library/Frameworks/{outer}.framework/Versions/A");
        let nested = format!("{parent}/Frameworks/{child}.framework/Versions/A/{child}");
        let bundle = |install: &str, content: &str| {
            let file = sdk
                .join(install.strip_prefix('/').unwrap())
                .with_extension("tbd");
            fs::create_dir_all(file.parent().unwrap()).unwrap();
            fs::write(&file, content).unwrap();
            file
        };
        let make_stub = |install: &str, exports: &str| {
            format!("--- !tapi-tbd\ntbd-version: 4\ninstall-name: '{install}'\n{exports}\n...\n")
        };
        let parent_install = format!("{parent}/{outer}");
        bundle(
            &parent_install,
            &make_stub(
                &parent_install,
                &format!(
                    "reexported-libraries:\n - targets: [ arm64-macos ]\n   libraries: [ '{nested}' ]"
                ),
            ),
        );
        let child_stub = make_stub(
            &nested,
            "exports:\n - targets: [ arm64-macos ]\n   symbols: [ _answer ]",
        );
        let child_file = bundle(&nested, &child_stub);
        let digest = || {
            let mut inputs = Inputs::default();
            library_inputs(
                &mut inputs,
                &search_roots(sdk, vec![])?,
                &BTreeSet::new(),
                &BTreeSet::from([outer.to_owned()]),
                sdk,
            )?;
            inputs.digest().ok()
        };
        let before = digest().unwrap();
        let modified = fs::metadata(&child_file).unwrap().modified().unwrap();
        fs::write(&child_file, child_stub.replace("_answer", "_bnswer")).unwrap();
        fs::File::open(&child_file)
            .unwrap()
            .set_times(fs::FileTimes::new().set_modified(modified))
            .unwrap();
        assert_ne!(digest().unwrap(), before);
        let unchanged = digest().unwrap();
        let shadow = frameworks.join(format!("{child}.framework/Versions/A/{child}.tbd"));
        fs::create_dir_all(shadow.parent().unwrap()).unwrap();
        fs::write(&shadow, &child_stub).unwrap();
        assert_ne!(digest().unwrap(), unchanged);
        let before_link = digest().unwrap();
        let versions = shadow.parent().unwrap().parent().unwrap();
        std::os::unix::fs::symlink("A", versions.join("Current")).unwrap();
        assert_ne!(digest().unwrap(), before_link);
        fs::write(shadow.with_extension(""), b"opaque framework binary").unwrap();
        assert!(digest().is_none());
        assert!(
            framework_chain(Path::new(
                "System/Library/PrivateFrameworks/Other.framework/Versions/A/Other"
            ))
            .is_none()
        );
        assert!(!framework_name("Other,Debug"));
    }
}
