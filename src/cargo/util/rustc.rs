use crate::util::data_structures::HashMap;
use std::env;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use anyhow::Context as _;
use cargo_util::{ProcessBuilder, ProcessError, paths};
use filetime::FileTime;
use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use crate::core::compiler::apply_env_config;
use crate::util::interning::InternedString;
use crate::util::{CargoResult, GlobalContext, StableHasher};

/// Information on the `rustc` executable
#[derive(Debug)]
pub struct Rustc {
    /// The location of the exe
    pub path: PathBuf,
    /// An optional program that will be passed the path of the rust exe as its first argument, and
    /// rustc args following this.
    pub wrapper: Option<PathBuf>,
    /// An optional wrapper to be used in addition to `rustc.wrapper` for workspace crates
    pub workspace_wrapper: Option<PathBuf>,
    /// Verbose version information (the output of `rustc -vV`)
    pub verbose_version: String,
    /// The rustc version (`1.23.4-beta.2`), this comes from `verbose_version`.
    pub version: semver::Version,
    /// The host triple (arch-platform-OS), this comes from `verbose_version`.
    pub host: InternedString,
    /// The rustc full commit hash, this comes from `verbose_version`.
    pub commit_hash: Option<String>,
    /// Lint-only arguments for the opt-in Clippy codegen workspace wrapper.
    pub(crate) ohm_clippy_codegen_args: Option<String>,
    ohm_clippy_configs: Mutex<HashMap<PathBuf, String>>,
    cache: Mutex<Cache>,
    transparent_unused_externs: OnceLock<bool>,
    ohm_incremental_codegen: OnceLock<bool>,
    ohm_incremental_mono_partitions: OnceLock<bool>,
    ohm_cloned_query_cache_prefix: OnceLock<bool>,
    bundled_clippy_wrapper: OnceLock<bool>,
}

impl Rustc {
    /// Runs the compiler at `path` to learn various pieces of information about
    /// it, with an optional wrapper.
    ///
    /// If successful this function returns a description of the compiler along
    /// with a list of its capabilities.
    #[tracing::instrument(skip(gctx))]
    pub fn new(
        path: PathBuf,
        wrapper: Option<PathBuf>,
        mut workspace_wrapper: Option<PathBuf>,
        rustup_rustc: &Path,
        cache_location: Option<PathBuf>,
        gctx: &GlobalContext,
    ) -> CargoResult<Rustc> {
        let ohm_clippy_codegen_args = if gctx.cli_unstable().ohm_clippy_codegen() {
            anyhow::ensure!(
                wrapper.is_none() && workspace_wrapper.is_none(),
                "-Zohm-clippy-codegen cannot be combined with a rustc wrapper or workspace wrapper"
            );
            let mut clippy_cache = Cache::load(
                None,
                None,
                &path,
                rustup_rustc,
                cache_location
                    .as_ref()
                    .map(|path| path.with_file_name(".ohm_clippy_codegen_info.json")),
                gctx,
            );
            workspace_wrapper = Some(ohm_clippy_codegen_driver(
                &path,
                rustup_rustc,
                gctx,
                &mut clippy_cache,
            )?);
            let lint_args = gctx
                .env_config()?
                .get("CARGO_OHM_CLIPPY_ARGS")
                .map(|value| {
                    value
                        .to_str()
                        .context("CARGO_OHM_CLIPPY_ARGS must be valid UTF-8")
                })
                .transpose()?
                .or_else(|| gctx.get_env("CARGO_OHM_CLIPPY_ARGS").ok())
                .unwrap_or_default();
            Some(encode_clippy_lint_args(lint_args)?)
        } else {
            None
        };
        let mut cache = Cache::load(
            wrapper.as_deref(),
            workspace_wrapper.as_deref(),
            &path,
            rustup_rustc,
            cache_location,
            gctx,
        );

        let mut cmd = ProcessBuilder::new(&path)
            .wrapped(workspace_wrapper.as_ref())
            .wrapped(wrapper.as_deref());
        if let Some(args) = &ohm_clippy_codegen_args {
            cmd.env("CLIPPY_CODEGEN", "1").env("CLIPPY_ARGS", args);
        }
        apply_env_config(gctx, &mut cmd)?;
        cmd.env(crate::CARGO_ENV, gctx.cargo_exe()?);
        cmd.arg("-vV");
        let verbose_version = cache.cached_output(&cmd, 0)?.0;

        let extract = |field: &str| -> CargoResult<&str> {
            verbose_version
                .lines()
                .find_map(|l| l.strip_prefix(field))
                .ok_or_else(|| {
                    anyhow::format_err!(
                        "`rustc -vV` didn't have a line for `{}`, got:\n{}",
                        field.trim(),
                        verbose_version
                    )
                })
        };

        let host = extract("host: ")?.into();
        let version = semver::Version::parse(extract("release: ")?).with_context(|| {
            format!(
                "rustc version does not appear to be a valid semver version, from:\n{}",
                verbose_version
            )
        })?;
        let commit_hash = extract("commit-hash: ").ok().map(|hash| {
            // Possible commit-hash values from rustc are SHA hex string and "unknown". See:
            // * https://github.com/rust-lang/rust/blob/531cb83fc/src/bootstrap/src/utils/channel.rs#L73
            // * https://github.com/rust-lang/rust/blob/531cb83fc/compiler/rustc_driver_impl/src/lib.rs#L911-L913
            #[cfg(debug_assertions)]
            if hash != "unknown" {
                debug_assert!(
                    hash.chars().all(|ch| ch.is_ascii_hexdigit()),
                    "commit hash must be a hex string, got: {hash:?}"
                );
                debug_assert!(
                    hash.len() == 40 || hash.len() == 64,
                    "hex string must be generated from sha1 or sha256 (i.e., it must be 40 or 64 characters long)\ngot: {hash:?}"
                );
            }
            hash.to_string()
        });

        Ok(Rustc {
            path,
            wrapper,
            workspace_wrapper,
            verbose_version,
            version,
            host,
            commit_hash,
            ohm_clippy_codegen_args,
            ohm_clippy_configs: Mutex::new(HashMap::default()),
            cache: Mutex::new(cache),
            transparent_unused_externs: OnceLock::new(),
            ohm_incremental_codegen: OnceLock::new(),
            ohm_incremental_mono_partitions: OnceLock::new(),
            ohm_cloned_query_cache_prefix: OnceLock::new(),
            bundled_clippy_wrapper: OnceLock::new(),
        })
    }

    /// Whether this compiler preserves ordinary lints while reporting unused externs.
    ///
    /// Probe through the configured workspace wrappers and reuse the existing
    /// compiler-information cache, which also remembers unsupported probes.
    pub fn supports_transparent_unused_externs(&self, gctx: &GlobalContext) -> bool {
        *self.transparent_unused_externs.get_or_init(|| {
            let mut process = self.workspace_process();
            if let Err(error) = apply_env_config(gctx, &mut process) {
                debug!("unable to configure unused-extern capability probe: {error}");
                return false;
            }
            process
                .arg("--error-format=json")
                .arg("--json=unused-externs-transparent")
                .arg("--print=sysroot");
            self.cached_output(&process, 0).is_ok()
        })
    }

    /// Whether this compiler supports both of Ohm's incremental codegen optimizations.
    ///
    /// Use the configured workspace wrappers and persistent compiler-information
    /// cache so older or custom compilers retain their ordinary behavior.
    pub fn supports_ohm_incremental_codegen(&self, gctx: &GlobalContext) -> bool {
        *self.ohm_incremental_codegen.get_or_init(|| {
            let mut process = self.workspace_process();
            if let Err(error) = apply_env_config(gctx, &mut process) {
                debug!("unable to configure incremental codegen capability probe: {error}");
                return false;
            }
            process
                .arg("-Zohm-caller-local-cgus")
                .arg("-Zohm-stable-cgu-merging")
                .arg("--print=sysroot");
            self.cached_output(&process, 0).is_ok()
        })
    }

    /// Whether this compiler can reuse monomorphization partitions without a public API hash.
    ///
    /// Keep this separate from the older codegen options so a previous Ohm compiler
    /// retains those optimizations when it cannot support this additional default.
    pub fn supports_ohm_incremental_mono_partitions(&self, gctx: &GlobalContext) -> bool {
        *self.ohm_incremental_mono_partitions.get_or_init(|| {
            let mut process = self.workspace_process();
            if let Err(error) = apply_env_config(gctx, &mut process) {
                debug!("unable to configure monomorphization partition capability probe: {error}");
                return false;
            }
            process
                .arg("-Zohm-incremental-mono-partitions")
                .arg("--print=sysroot");
            self.cached_output(&process, 0).is_ok()
        })
    }

    /// Gets a process builder set up to use the found rustc version, with a wrapper if `Some`.
    pub fn process(&self) -> ProcessBuilder {
        let mut cmd = ProcessBuilder::new(self.path.as_path()).wrapped(self.wrapper.as_ref());
        cmd.retry_with_argfile(true);
        cmd
    }

    /// Gets a process builder set up to use the found rustc version, with a wrapper if `Some`.
    pub fn workspace_process(&self) -> ProcessBuilder {
        let mut cmd = ProcessBuilder::new(self.path.as_path())
            .wrapped(self.workspace_wrapper.as_ref())
            .wrapped(self.wrapper.as_ref());
        if let Some(args) = &self.ohm_clippy_codegen_args {
            cmd.env("CLIPPY_CODEGEN", "1").env("CLIPPY_ARGS", args);
        }
        cmd.retry_with_argfile(true);
        cmd
    }

    pub fn process_no_wrapper(&self) -> ProcessBuilder {
        let mut cmd = ProcessBuilder::new(&self.path);
        cmd.retry_with_argfile(true);
        cmd
    }

    /// Checks whether the selected compiler can clone retained query-cache prefixes.
    pub fn supports_ohm_cloned_query_cache_prefix(&self, gctx: &GlobalContext) -> bool {
        *self.ohm_cloned_query_cache_prefix.get_or_init(|| {
            let mut process = self.workspace_process();
            if let Err(error) = apply_env_config(gctx, &mut process) {
                debug!("unable to configure query-cache clone capability probe: {error}");
                return false;
            }
            process
                .arg("-Zohm-cloned-query-cache-prefix")
                .arg("--print=sysroot");
            self.cached_output(&process, 0).is_ok()
        })
    }

    /// Recognizes only the selected toolchain's own matching Clippy driver.
    ///
    /// This permits isolating its private outputs, not importing its diagnostics
    /// or trusting arbitrary wrappers. The caller must also validate the compiler
    /// and its loader environment before using this result.
    pub(crate) fn has_bundled_clippy_wrapper(&self, gctx: &GlobalContext, sysroot: &Path) -> bool {
        *self.bundled_clippy_wrapper.get_or_init(|| {
            let Some(wrapper) = &self.workspace_wrapper else {
                return false;
            };
            if self.wrapper.is_some() || self.ohm_clippy_codegen_args.is_some() {
                return false;
            }
            let Ok(bin) = sysroot.join("bin").canonicalize() else {
                return false;
            };
            let Ok(expected) = bin
                .join("clippy-driver")
                .with_extension(env::consts::EXE_EXTENSION)
                .canonicalize()
            else {
                return false;
            };
            if expected.parent() != Some(bin.as_path())
                || wrapper.canonicalize().ok().as_ref() != Some(&expected)
            {
                return false;
            }
            // `verbose_version` was obtained through the workspace wrapper, so
            // Clippy can report its own version while ignoring the selected rustc.
            // Probe rustc separately. Cache keys do not include the executable;
            // distinguish this unwrapped probe from the initial wrapped `-vV`.
            let mut rustc = self.process_no_wrapper();
            if apply_env_config(gctx, &mut rustc).is_err() {
                return false;
            }
            rustc.arg("-vV");
            let mut fingerprint = StableHasher::new();
            ("ohm-unwrapped-rustc-version-v1", &self.path).hash(&mut fingerprint);
            let Ok((rustc_version, _)) = self.cached_output(&rustc, Hasher::finish(&fingerprint)) else {
                return false;
            };
            let mut process = ProcessBuilder::new(expected);
            if apply_env_config(gctx, &mut process).is_err() {
                return false;
            }
            process.args(&["--rustc", "-vV"]);
            self.cached_output(&process, 0)
                .is_ok_and(|(version, _)| version == rustc_version)
        })
    }

    /// Tracks Clippy config discovery, including a config appearing after a fresh build.
    pub(crate) fn ohm_clippy_config_fingerprint(
        &self,
        package_root: &Path,
        gctx: &GlobalContext,
    ) -> CargoResult<String> {
        let mut configs = self.ohm_clippy_configs.lock().unwrap();
        if let Some(fingerprint) = configs.get(package_root) {
            return Ok(fingerprint.clone());
        }
        let configured = gctx
            .env_config()?
            .get("CLIPPY_CONF_DIR")
            .map(|value| value.as_os_str())
            .or_else(|| gctx.get_env_os("CLIPPY_CONF_DIR"));
        let mut directory = configured
            .map_or_else(
                || package_root.to_path_buf(),
                |value| package_root.join(value),
            )
            .canonicalize()?;
        let mut hasher = StableHasher::new();
        directory.hash(&mut hasher);
        loop {
            let mut found = false;
            // Match Clippy's upward search and dotfile precedence. The second
            // path also matters because its presence produces a warning.
            for name in [".clippy.toml", "clippy.toml"] {
                if let Ok(path) = directory.join(name).canonicalize() {
                    if !path.is_dir() {
                        path.hash(&mut hasher);
                        if !found {
                            std::fs::read(&path)?.hash(&mut hasher);
                        }
                        found = true;
                    }
                }
            }
            if found || !directory.pop() {
                break;
            }
        }
        let fingerprint = crate::util::to_hex(Hasher::finish(&hasher));
        configs.insert(package_root.to_path_buf(), fingerprint.clone());
        Ok(fingerprint)
    }

    /// Gets the output for the given command.
    ///
    /// This will return the cached value if available, otherwise it will run
    /// the command and cache the output.
    ///
    /// `extra_fingerprint` is extra data to include in the cache fingerprint.
    /// Use this if there is other information about the environment that may
    /// affect the output that is not part of `cmd`.
    ///
    /// Returns a tuple of strings `(stdout, stderr)`.
    pub fn cached_output(
        &self,
        cmd: &ProcessBuilder,
        extra_fingerprint: u64,
    ) -> CargoResult<(String, String)> {
        self.cache
            .lock()
            .unwrap()
            .cached_output(cmd, extra_fingerprint)
    }
}

/// Selects the capability-checked Clippy driver from the selected compiler's sysroot.
fn ohm_clippy_codegen_driver(
    rustc: &Path,
    rustup_rustc: &Path,
    gctx: &GlobalContext,
    cache: &mut Cache,
) -> CargoResult<PathBuf> {
    let mut output = |tool: &Path, args: &[&str], fingerprint| -> CargoResult<String> {
        let mut process = ProcessBuilder::new(tool);
        apply_env_config(gctx, &mut process)?;
        process.args(args);
        Ok(cache.cached_output(&process, fingerprint)?.0)
    };
    let sysroot = output(rustc, &["--print", "sysroot"], 0)?;
    let driver = Path::new(sysroot.trim())
        .join("bin/clippy-driver")
        .with_extension(env::consts::EXE_EXTENSION);
    // The selected compiler keys this cache; each driver probe additionally
    // tracks the driver executable so replacing it cannot preserve admission.
    let driver_fingerprint = rustc_fingerprint(None, Some(&driver), rustc, rustup_rustc, gctx)
        .with_context(|| {
            format!(
                "-Zohm-clippy-codegen requires a Clippy driver at {}",
                driver.display()
            )
        })?;
    let capability = output(
        &driver,
        &["--ohm-clippy-codegen-version"],
        driver_fingerprint,
    )
    .with_context(|| {
        format!(
            "-Zohm-clippy-codegen requires a compatible Ohm Clippy driver at {}",
            driver.display()
        )
    })?;
    anyhow::ensure!(
        capability.trim() == "ohm-clippy-codegen-v1",
        "{} does not support -Zohm-clippy-codegen",
        driver.display()
    );
    anyhow::ensure!(
        output(&driver, &["--rustc", "-vV"], driver_fingerprint)? == output(rustc, &["-vV"], 0)?,
        "-Zohm-clippy-codegen requires Clippy and rustc from the same compiler build"
    );
    Ok(driver)
}

/// Allows lint levels without letting Clippy-only arguments change the compiled program.
fn encode_clippy_lint_args(value: &str) -> CargoResult<String> {
    let args = value.split_whitespace().collect::<Vec<_>>();
    let mut remaining = args.as_slice();
    while let Some((arg, rest)) = remaining.split_first() {
        remaining = rest;
        let lint = if matches!(
            *arg,
            "-A" | "-W" | "-D" | "-F" | "--allow" | "--warn" | "--deny" | "--forbid"
        ) {
            let Some((lint, rest)) = remaining.split_first() else {
                anyhow::bail!("CARGO_OHM_CLIPPY_ARGS: {arg} requires a lint name");
            };
            remaining = rest;
            *lint
        } else if let Some(lint) = [
            "--allow=",
            "--warn=",
            "--deny=",
            "--forbid=",
            "-A",
            "-W",
            "-D",
            "-F",
        ]
        .iter()
        .find_map(|prefix| arg.strip_prefix(prefix))
        {
            lint
        } else {
            anyhow::bail!(
                "CARGO_OHM_CLIPPY_ARGS accepts only lint levels (-A, -W, -D, -F), found `{arg}`"
            );
        };
        anyhow::ensure!(
            !lint.is_empty()
                && !lint.contains("__CLIPPY_HACKERY__")
                && lint
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b':' | b'-')),
            "CARGO_OHM_CLIPPY_ARGS contains an invalid lint name `{lint}`"
        );
    }
    Ok(args.join("__CLIPPY_HACKERY__"))
}

/// It is a well known fact that `rustc` is not the fastest compiler in the
/// world.  What is less known is that even `rustc --version --verbose` takes
/// about a hundred milliseconds! Because we need compiler version info even
/// for no-op builds, we cache it here, based on compiler's mtime and rustup's
/// current toolchain.
///
/// <https://github.com/rust-lang/cargo/issues/5315>
/// <https://github.com/rust-lang/rust/issues/49761>
#[derive(Debug)]
struct Cache {
    cache_location: Option<PathBuf>,
    dirty: bool,
    data: CacheData,
}

#[derive(Serialize, Deserialize, Debug, Default)]
struct CacheData {
    rustc_fingerprint: u64,
    outputs: HashMap<u64, Output>,
    successes: HashMap<u64, bool>,
}

#[derive(Serialize, Deserialize, Debug)]
struct Output {
    success: bool,
    status: String,
    code: Option<i32>,
    stdout: String,
    stderr: String,
}

impl Cache {
    fn load(
        wrapper: Option<&Path>,
        workspace_wrapper: Option<&Path>,
        rustc: &Path,
        rustup_rustc: &Path,
        cache_location: Option<PathBuf>,
        gctx: &GlobalContext,
    ) -> Cache {
        match (
            cache_location,
            rustc_fingerprint(wrapper, workspace_wrapper, rustc, rustup_rustc, gctx),
        ) {
            (Some(cache_location), Ok(rustc_fingerprint)) => {
                let empty = CacheData {
                    rustc_fingerprint,
                    outputs: HashMap::default(),
                    successes: HashMap::default(),
                };
                let mut dirty = true;
                let data = match read(&cache_location) {
                    Ok(data) => {
                        if data.rustc_fingerprint == rustc_fingerprint {
                            debug!("reusing existing rustc info cache");
                            dirty = false;
                            data
                        } else {
                            debug!("different compiler, creating new rustc info cache");
                            empty
                        }
                    }
                    Err(e) => {
                        debug!("failed to read rustc info cache: {}", e);
                        empty
                    }
                };
                return Cache {
                    cache_location: Some(cache_location),
                    dirty,
                    data,
                };

                fn read(path: &Path) -> CargoResult<CacheData> {
                    let json = paths::read(path)?;
                    Ok(serde_json::from_str(&json)?)
                }
            }
            (_, fingerprint) => {
                if let Err(e) = fingerprint {
                    warn!("failed to calculate rustc fingerprint: {}", e);
                }
                debug!("rustc info cache disabled");
                Cache {
                    cache_location: None,
                    dirty: false,
                    data: CacheData::default(),
                }
            }
        }
    }

    fn cached_output(
        &mut self,
        cmd: &ProcessBuilder,
        extra_fingerprint: u64,
    ) -> CargoResult<(String, String)> {
        let key = process_fingerprint(cmd, extra_fingerprint);
        if let std::collections::hash_map::Entry::Vacant(e) = self.data.outputs.entry(key) {
            debug!("rustc info cache miss");
            debug!("running {}", cmd);
            let output = cmd.output()?;
            let stdout = String::from_utf8(output.stdout)
                .map_err(|e| anyhow::anyhow!("{}: {:?}", e, e.as_bytes()))
                .with_context(|| format!("`{}` didn't return utf8 output", cmd))?;
            let stderr = String::from_utf8(output.stderr)
                .map_err(|e| anyhow::anyhow!("{}: {:?}", e, e.as_bytes()))
                .with_context(|| format!("`{}` didn't return utf8 output", cmd))?;
            e.insert(Output {
                success: output.status.success(),
                status: if output.status.success() {
                    String::new()
                } else {
                    cargo_util::exit_status_to_string(output.status)
                },
                code: output.status.code(),
                stdout,
                stderr,
            });
            self.dirty = true;
        } else {
            debug!("rustc info cache hit");
        }
        let output = &self.data.outputs[&key];
        if output.success {
            Ok((output.stdout.clone(), output.stderr.clone()))
        } else {
            Err(ProcessError::new_raw(
                &format!("process didn't exit successfully: {}", cmd),
                output.code,
                &output.status,
                Some(output.stdout.as_ref()),
                Some(output.stderr.as_ref()),
            )
            .into())
        }
    }
}

impl Drop for Cache {
    fn drop(&mut self) {
        if !self.dirty {
            return;
        }
        if let Some(ref path) = self.cache_location {
            let json = serde_json::to_string(&self.data).unwrap();
            match paths::write(path, json.as_bytes()) {
                Ok(()) => info!("updated rustc info cache"),
                Err(e) => warn!("failed to update rustc info cache: {}", e),
            }
        }
    }
}

fn rustc_fingerprint(
    wrapper: Option<&Path>,
    workspace_wrapper: Option<&Path>,
    rustc: &Path,
    rustup_rustc: &Path,
    gctx: &GlobalContext,
) -> CargoResult<u64> {
    let mut hasher = StableHasher::new();

    let hash_exe = |hasher: &mut _, path| -> CargoResult<()> {
        let path = paths::resolve_executable(path)?;
        path.hash(hasher);

        let meta = paths::metadata(&path)?;
        meta.len().hash(hasher);

        // Often created and modified are the same, but not all filesystems support the former,
        // and distro reproducible builds may clamp the latter, so we try to use both.
        FileTime::from_creation_time(&meta).hash(hasher);
        FileTime::from_last_modification_time(&meta).hash(hasher);
        Ok(())
    };

    hash_exe(&mut hasher, rustc)?;
    if let Some(wrapper) = wrapper {
        hash_exe(&mut hasher, wrapper)?;
    }
    if let Some(workspace_wrapper) = workspace_wrapper {
        hash_exe(&mut hasher, workspace_wrapper)?;
    }

    // Rustup can change the effective compiler without touching
    // the `rustc` binary, so we try to account for this here.
    // If we see rustup's env vars, we mix them into the fingerprint,
    // but we also mix in the mtime of the actual compiler (and not
    // the rustup shim at `~/.cargo/bin/rustup`), because `RUSTUP_TOOLCHAIN`
    // could be just `stable-x86_64-unknown-linux-gnu`, i.e, it could
    // not mention the version of Rust at all, which changes after
    // `rustup update`.
    //
    // If we don't see rustup env vars, but it looks like the compiler
    // is managed by rustup, we conservatively bail out.
    let maybe_rustup = rustup_rustc == rustc;
    match (
        maybe_rustup,
        gctx.get_env("RUSTUP_HOME"),
        gctx.get_env("RUSTUP_TOOLCHAIN"),
    ) {
        (_, Ok(rustup_home), Ok(rustup_toolchain)) => {
            debug!("adding rustup info to rustc fingerprint");
            rustup_toolchain.hash(&mut hasher);
            rustup_home.hash(&mut hasher);
            let real_rustc = Path::new(&rustup_home)
                .join("toolchains")
                .join(rustup_toolchain)
                .join("bin")
                .join("rustc")
                .with_extension(env::consts::EXE_EXTENSION);
            paths::mtime(&real_rustc)?.hash(&mut hasher);
        }
        (true, _, _) => anyhow::bail!("probably rustup rustc, but without rustup's env vars"),
        _ => (),
    }

    Ok(Hasher::finish(&hasher))
}

fn process_fingerprint(cmd: &ProcessBuilder, extra_fingerprint: u64) -> u64 {
    let mut hasher = StableHasher::new();
    extra_fingerprint.hash(&mut hasher);
    cmd.get_args().for_each(|arg| arg.hash(&mut hasher));
    let mut env = cmd.get_envs().iter().collect::<Vec<_>>();
    env.sort_unstable();
    env.hash(&mut hasher);
    Hasher::finish(&hasher)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn bundled_clippy_requires_the_unwrapped_compiler_version() {
        let version = "rustc 1.98.0\nbinary: rustc\ncommit-hash: unknown\nhost: x86_64-unknown-linux-gnu\nrelease: 1.98.0\n";
        for (selected_version, admitted) in [
            (Some(version.to_owned()), true),
            (Some(version.replace("1.98.0", "1.97.0")), false),
            (None, false),
        ] {
            let root = tempfile::tempdir().unwrap();
            let bin = root.path().join("bin");
            fs::create_dir(&bin).unwrap();
            let rustc = bin.join("rustc");
            let clippy = bin.join("clippy-driver");
            for (path, output) in [
                (&rustc, selected_version.as_deref()),
                (&clippy, Some(version)),
            ] {
                let script = match output {
                    Some(output) => format!("#!/bin/sh\ncat <<'VERSION'\n{output}VERSION\n"),
                    None => "#!/bin/sh\nexit 1\n".to_owned(),
                };
                fs::write(path, script).unwrap();
                fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
            }
            let gctx = GlobalContext::new(
                cargo_util_terminal::Shell::new(),
                root.path().to_path_buf(),
                root.path().join("cargo-home"),
            );
            let compiler = Rustc::new(
                rustc,
                None,
                Some(clippy.clone()),
                Path::new("unused-rustup-proxy"),
                None,
                &gctx,
            )
            .unwrap();
            assert_eq!(compiler.verbose_version, version);

            // A wrapped version already cached under identical arguments must
            // not answer the unwrapped probe: process keys omit the executable.
            let mut wrapped = ProcessBuilder::new(clippy);
            apply_env_config(&gctx, &mut wrapped).unwrap();
            wrapped.arg("-vV");
            assert_eq!(compiler.cached_output(&wrapped, 0).unwrap().0, version);
            assert_eq!(
                compiler.has_bundled_clippy_wrapper(&gctx, root.path()),
                admitted
            );
        }
    }
}
