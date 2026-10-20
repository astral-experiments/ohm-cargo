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

use crate::compiler::apply_env_config;
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
    cache: Mutex<Cache>,
    transparent_unused_externs: OnceLock<bool>,
    ohm_incremental_codegen: OnceLock<bool>,
    ohm_incremental_mono_partitions: OnceLock<bool>,
    ohm_shared_stages: OnceLock<bool>,
    ohm_thinlto_cache: OnceLock<bool>,
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
        workspace_wrapper: Option<PathBuf>,
        rustup_rustc: &Path,
        cache_location: Option<PathBuf>,
        gctx: &GlobalContext,
    ) -> CargoResult<Rustc> {
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
            cache: Mutex::new(cache),
            transparent_unused_externs: OnceLock::new(),
            ohm_incremental_codegen: OnceLock::new(),
            ohm_incremental_mono_partitions: OnceLock::new(),
            ohm_shared_stages: OnceLock::new(),
            ohm_thinlto_cache: OnceLock::new(),
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

    /// Whether this compiler tracks check/build output mode as a query dependency.
    pub fn supports_ohm_shared_stages(&self, gctx: &GlobalContext) -> bool {
        *self.ohm_shared_stages.get_or_init(|| {
            // Units compiled through a workspace wrapper do not share stages.
            let mut process = self.process();
            if let Err(error) = apply_env_config(gctx, &mut process) {
                debug!("unable to configure shared stages capability probe: {error}");
                return false;
            }
            process.arg("-Zohm-shared-stages").arg("--print=sysroot");
            self.cached_output(&process, 0).is_ok()
        })
    }

    /// Older compilers keep their normal backend when they lack the cache option.
    pub fn supports_ohm_thinlto_cache(&self, gctx: &GlobalContext) -> bool {
        *self.ohm_thinlto_cache.get_or_init(|| {
            let mut process = self.workspace_process();
            if let Err(error) = apply_env_config(gctx, &mut process) {
                debug!("unable to configure ThinLTO cache capability probe: {error}");
                return false;
            }
            process.arg("-Zthinlto-cache=.").arg("--print=sysroot");
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
        cmd.retry_with_argfile(true);
        cmd
    }

    pub fn process_no_wrapper(&self) -> ProcessBuilder {
        let mut cmd = ProcessBuilder::new(&self.path);
        cmd.retry_with_argfile(true);
        cmd
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
            if self.wrapper.is_some() {
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
            let mut process = ProcessBuilder::new(expected);
            if apply_env_config(gctx, &mut process).is_err() {
                return false;
            }
            process.args(&["--rustc", "-vV"]);
            let Ok((clippy_version, _)) = self.cached_output(&process, 0) else {
                return false;
            };
            // `verbose_version` was obtained through the workspace wrapper, so it
            // alone cannot prove that the selected rustc matches Clippy's compiler.
            let mut compiler = ProcessBuilder::new(&self.path);
            if apply_env_config(gctx, &mut compiler).is_err() {
                return false;
            }
            compiler.arg("-vV");
            let fingerprint = crate::util::hash_u64(("ohm-clippy-seed-rustc-v1", &self.path));
            self.cached_output(&compiler, fingerprint)
                .is_ok_and(|(version, _)| {
                    version == clippy_version && version == self.verbose_version
                })
        })
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
    // Keep the active compiler in the legacy top-level format. One separate,
    // nonrecursive context supports alternating between rustc and a wrapper.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    previous: Option<CompilerCacheData>,
}

#[derive(Serialize, Deserialize, Debug, Default)]
struct CompilerCacheData {
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
                let empty = CompilerCacheData {
                    rustc_fingerprint,
                    outputs: HashMap::default(),
                    successes: HashMap::default(),
                };
                let mut dirty = true;
                let data = match read(&cache_location) {
                    Ok(mut data) => {
                        if data.rustc_fingerprint == rustc_fingerprint {
                            debug!("reusing existing rustc info cache");
                            dirty = false;
                            data
                        } else {
                            let selected = if let Some(previous) = data.previous.take()
                                && previous.rustc_fingerprint == rustc_fingerprint
                            {
                                debug!("reusing previous rustc info cache");
                                previous
                            } else {
                                debug!("different compiler, creating new rustc info cache");
                                empty
                            };
                            data.previous = Some(CompilerCacheData {
                                rustc_fingerprint: std::mem::replace(
                                    &mut data.rustc_fingerprint,
                                    selected.rustc_fingerprint,
                                ),
                                outputs: std::mem::replace(&mut data.outputs, selected.outputs),
                                successes: std::mem::replace(
                                    &mut data.successes,
                                    selected.successes,
                                ),
                            });
                            data
                        }
                    }
                    Err(e) => {
                        debug!("failed to read rustc info cache: {}", e);
                        CacheData {
                            rustc_fingerprint: empty.rustc_fingerprint,
                            outputs: empty.outputs,
                            successes: empty.successes,
                            previous: None,
                        }
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

#[cfg(test)]
mod cache_tests {
    use super::*;

    #[test]
    fn compiler_cache_preserves_legacy_json() {
        let legacy = serde_json::json!({
            "rustc_fingerprint": 123,
            "outputs": {
                "2": {
                    "success": true,
                    "status": "",
                    "code": 0,
                    "stdout": "rustc 1.99.0\n",
                    "stderr": "probe diagnostic\n",
                },
            },
            "successes": {"1": true},
        });
        let mut cache: CacheData = serde_json::from_value(legacy.clone()).unwrap();
        assert!(cache.previous.is_none());
        assert_eq!(serde_json::to_value(&cache).unwrap(), legacy);

        cache.previous = Some(CompilerCacheData {
            rustc_fingerprint: 456,
            ..CompilerCacheData::default()
        });
        let serialized = serde_json::to_value(&cache).unwrap();
        let old_reader: CompilerCacheData = serde_json::from_value(serialized.clone()).unwrap();
        assert_eq!(serde_json::to_value(old_reader).unwrap(), legacy);
        let new_reader: CacheData = serde_json::from_value(serialized).unwrap();
        assert_eq!(new_reader.previous.unwrap().rustc_fingerprint, 456);
    }
}

#[cfg(all(test, unix))]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

    use super::*;

    #[test]
    fn bundled_clippy_requires_the_unwrapped_compiler_version_and_path() {
        let root = tempfile::tempdir().unwrap();
        let bin = root.path().join("bin");
        fs::create_dir(&bin).unwrap();
        let compiler = bin.join("rustc");
        let clippy = bin.join("clippy-driver");
        let write_tool = |path: &Path, version: &str| {
            fs::write(path, format!(
                "#!/bin/sh\nprintf '%s\\n' 'rustc {version}\nbinary: rustc\nhost: x86_64-unknown-linux-gnu\nrelease: {version}\n'\n"
            )).unwrap();
            fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
        };
        write_tool(&compiler, "1.98.0");
        write_tool(&clippy, "1.98.0");
        let context = GlobalContext::default().unwrap();
        let selected = |wrapper: &Path| {
            Rustc::new(
                compiler.clone(),
                None,
                Some(wrapper.to_path_buf()),
                &compiler,
                None,
                &context,
            )
            .unwrap()
        };
        assert!(selected(&clippy).has_bundled_clippy_wrapper(&context, root.path()));

        // Both wrapper-based probes still report 1.98.0. The unwrapped compiler
        // must be checked independently rather than trusting those identical answers.
        write_tool(&compiler, "1.99.0");
        assert!(!selected(&clippy).has_bundled_clippy_wrapper(&context, root.path()));
        write_tool(&compiler, "1.98.0");
        let external = root.path().join("external-clippy");
        write_tool(&external, "1.98.0");
        assert!(!selected(&external).has_bundled_clippy_wrapper(&context, root.path()));
        fs::remove_file(&clippy).unwrap();
        std::os::unix::fs::symlink(&external, &clippy).unwrap();
        assert!(!selected(&clippy).has_bundled_clippy_wrapper(&context, root.path()));
    }
}
