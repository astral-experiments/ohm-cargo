# Lazy libgit2 policy: design and repository-entry audit

This is a read-only design review of `work/ohm-cargo`, not an implementation.
The profiling evidence is in `attribution.md`. The CLI initialization region
accounts for 184,529,209 Ir (9.40%) in one diagnostic no-op `check` profile;
175,277,155 Ir is default TLS verification-path loading. This is an upper bound
on a candidate's Cargo instruction savings, not a predicted native speedup.

## Proposed change

Keep the current owner-validation option setter and its binary-only policy in
`src/bin/cargo/main.rs:429`. Change `cli.rs:97` to register this function as a
callback in a small Cargo-library helper, then apply the callback once before
Cargo's first libgit2 repository access. Do not disable owner validation in the
library unless the binary explicitly registered its policy.

The helper can live in a private `util/git.rs` module, with only its registration
function re-exported publicly for the separate binary crate. Repository code
uses a crate-private `ensure_git2_policy()` helper. Two pieces of state suffice:

```rust
static INITIALIZER: OnceLock<fn()> = OnceLock::new();
static INITIALIZED: Once = Once::new();

pub(crate) fn ensure_git2_policy() {
    if let Some(initialize) = INITIALIZER.get() {
        INITIALIZED.call_once(*initialize);
    }
}
```

Registration must reject duplicate registration and be documented as a startup
operation before command execution. Do not complete `INITIALIZED` when no
callback is registered: ordinary library use must remain a no-op, and an early
unregistered call must not silently consume a later registration. The callback
must not recursively invoke this helper. A panic from the existing option
setter must prevent the repository operation, rather than be swallowed.

The binary registers at the existing CLI initialization point, after successful
configuration and before `exec.exec`. Help, version, list, and explain branches
retain their current behavior. The callback continues to call the supported
`git2::opts::set_verify_owner_validation(false)` API. That API performs normal
git2/libgit2 initialization before setting the option. Do not call raw
`git_libgit2_opts` before initialization, even though today's C implementation
of this option is a simple assignment: `git2/global.h:23` explicitly requires
initialization before other libgit2 calls.

A `GlobalContext` field is less attractive for this narrowly scoped change:
`GitRepo::init`, `GitRepo::discover`, `GitRemote::db_at`, and corruption-recovery
helpers currently have no context parameter. Threading one through these APIs
would be broader than the process-global option being deferred.

## Preserve startup certificate-environment behavior

The current setter does more than set the owner policy. `git2-0.21.0/src/lib.rs`
initializes its environment once, then calls `libgit2_sys::init`. On Unix HTTPS
builds except macOS/iOS, the environment step calls
`openssl_probe::init_ssl_cert_env_vars()` (`lib.rs:895`). This can populate or
repair `SSL_CERT_FILE` and `SSL_CERT_DIR` before Cargo launches rustc, build
scripts, external subcommands, or other child processes.

Modern curl does not duplicate this behavior at startup. `curl-0.4.50/build.rs`
enables its `need_openssl_init` cfg only for OpenSSL older than 1.1.0; its startup
certificate-environment call is guarded by that cfg. Calling `curl::init()` is
therefore not a substitute on the measured host.

For equivalent child environments, retain the cheap certificate probe at the
existing CLI initialization point while deferring the expensive libgit2/TLS
context construction. Add a direct dependency on the already-locked
`openssl-probe` 0.1.6, with the same Unix/not-macOS/not-iOS cfg as git2's
environment step, and use its supported unsafe `init_openssl_env_vars` API with
an explicit startup-safety rationale. Cargo's git2 dependency always enables
HTTPS. Preserve valid caller-provided paths; preserve the existing probe's
handling of absent or invalid paths instead of substituting hard-coded paths.

The normal later git2 initializer still probes again before its own TLS setup.
With unchanged valid values it avoids `setenv`. This is a timing concern to
review before implementation is accepted: deferral must not introduce a first
environment write from a worker thread. Establish when each initial repository
entry can run, and test child environments with unset, valid, and invalid
certificate variables. File/environment changes between startup and the first
Git operation may cause git2's internal probe to choose a new value; do not
claim full equivalence under that race without an explicit decision. Avoid
adding an unsupported raw-libgit2 initialization shortcut to bypass this issue.

## Remove the second eager trigger

`GlobalContext::http_config` calls `disables_multiplexing_for_bad_curl`.
Currently `context/mod.rs:2734` performs `http_proxy_exists` first, which reads
Git's global config through `git2::Config::open_default` and would simply move
the 184M-instruction initialization later if the CLI call alone were removed.

Evaluate these predicates in this order:

1. Is `http.multiplexing` unspecified?
2. Does the curl version match one of the existing bad-version prefixes?
3. Does a proxy exist, using the current lookup and precedence?

Only then set multiplexing to false. Keep the existing `starts_with` semantics
for `7.87.0`, `7.88.0`, and `7.88.1`; do not silently change version matching.
Actual network-handle setup continues to read the proxy configuration as before.
`git2::Config` operations need no owner-policy override themselves: they do not
open a repository. A later repository entry applies the registered policy even
if a config lookup has already initialized the libgit2 runtime.

## Repository-entry inventory

All line numbers refer to the inspected main checkout. Prefer applying the
guard next to every production constructor, including reopens, so future
refactors cannot accidentally bypass it. A small set of guarded constructor
wrappers is also reasonable; it must cover the builder clone path explicitly.

| Location | Operation and reachability | Required treatment |
| --- | --- | --- |
| `sources/git/utils.rs:156` | `GitRemote::db_at`, opens a cached Git database | Initial entry; guard before open. |
| `sources/git/utils.rs:1549` | Local `init(path, bare)` used for fresh checkout and recovery | Initial entry; guard before constructing options/init. |
| `sources/git/oxide.rs:366` | `reinitialize` has an inner libgit2 init helper, including recovery from a gix operation | Current caller holds a libgit2 repository already; guard the inner helper too so its constructor is locally covered. |
| `sources/registry/git_remote.rs:109` | `GitRemoteRegistry::repo`, opens index or initializes fallback | Guard once inside the empty-cache branch before open; this covers both constructors at116 and139. |
| `util/vcs.rs:34` | `GitRepo::init`, used by project creation | Initial entry; guard before init. |
| `util/vcs.rs:38` | `GitRepo::discover`, also used by `existing_vcs_repo` | Initial entry; guard before discovery. |
| `ops/cargo_worktree/mod.rs:38` | `worktree_add`, discovers donor repository | Initial entry after workspace loading; guard before discovery. |
| `ops/cargo_fix/mod.rs:241` | Status check directly discovers repository | Today an earlier `existing_vcs_repo` goes through `GitRepo::discover`; still guard this direct constructor or route through the guarded helper. |
| `sources/git/utils.rs:179` | `GitDatabase::copy_to`, opens existing checkout | Holds an already-open database; guard adjacent to the constructor for complete coverage. |
| `sources/git/utils.rs:299–335` | `GitCheckout::clone_into`, `RepoBuilder::clone` after local config creation | Holds an already-open database; explicitly guard this builder entry as well. |
| `sources/git/utils.rs:1328` | Reopen after gix corruption recovery | Existing libgit2 repository already present; retain explicit constructor guard. |
| `sources/git/utils.rs:1476` | Reopen after successful external `git gc` | Existing libgit2 repository already present; retain explicit constructor guard. |
| `sources/git/utils.rs:476` | `Submodule::open` | Reached through a parent repository created by a guarded entry; document/test this ownership chain. |

`utils.rs:1750` is test-only repository construction. Constructors in
`crates/cargo-test-support` and tests are fixture setup, not Cargo binary
production entry points. `crates/xtask-bump-check` is a separate binary that does
not currently use the Cargo CLI's owner override; do not silently change it.

`bin/cargo/cli.rs:226` uses `git2::Version::get`, which currently reads static
version/features without calling `git2::init`; leave that behavior alone.
`util/network/proxy.rs:22` is the only production independent Git-config lookup
found outside Git-source code. Other credentials, objects, refs, statuses, and
fetch operations are downstream of existing repository objects.

The gix retry callback runs in a scoped worker thread
(`sources/git/oxide.rs:34–59`). Its only current `reinitialize` caller is
`utils.rs:1317`, inside `fetch_with_gitoxide`, whose argument is already a
`&mut git2::Repository`. Thus this recovery currently cannot be the binary's
first Git initialization if the constructor guards above are installed.
`GitSource::fetch_db` opens the database at `source.rs:189` before invoking a
fetch. The direct new/init, fix, and worktree entries are synchronous command
paths. This establishes the specific worker ancestry checked here; it does not
turn a library embedding application's arbitrary thread usage into a startup
safety guarantee.

Do not move `init_git_transports` (`sources/git/utils.rs:1420`) into the new
callback. Its separate once guard is in `fetch_with_libgit2`, and its custom
curl transport depends on `GlobalContext`, HTTP configuration, and existing
transport-registration synchronization. Preserve it and the certificate and
SSH-host callbacks as they are.

## Validation before a performance claim

Use fresh processes for tests that inspect global libgit2 options or the
registered callback. A process that previously disabled validation cannot prove
the library default. libgit2 has `GIT_OPT_GET_OWNER_VALIDATION`, but git2 has no
public getter: any test using the raw getter must first initialize through a
supported git2 API, then query it. Never query raw options before initialization.

- Exercise unregistered library use and assert owner validation remains enabled;
  exercise binary registration plus a repository operation and assert it is
  disabled before that operation. Independently verify that registration alone
  does not execute the callback.
- Test the helper state with concurrent callers, exactly-once execution, and an
  unregistered call followed by registration. This can use an isolated state
  object plus a counting callback; avoid global-state test-order assumptions.
- Cover fresh local Git dependency acquisition, cached/offline Git dependencies,
  local clone/submodules, Git registry open/init, and both corruption-recovery
  helpers. Include the gix recovery route and confirm that the parent repository
  was guarded before its retry worker started.
- Run existing project-new/init, fix dirty/staged-repository checks, and Ohm
  worktree tests. Verify custom HTTP proxy/TLS configuration still reaches the
  existing transport code and SSH known-host checks retain their behavior.
- Extend the existing curl workaround test matrix with explicit `Some(true)`
  and version suffixes, retaining proxy/env precedence. Verify unaffected curl
  and explicit multiplexing avoid the Git-config lookup, while affected curl
  still consults it. A fresh-process trace/profile can prove the absence of
  runtime initialization on the no-Git path without a brittle source-text test.
- Compare the child process's certificate environment under baseline/candidate
  for unset, valid custom, and invalid SSL variables. Confirm actual HTTPS Git
  operations still initialize their normal trust store; do not use disabled
  certificate verification as a test shortcut.
- Re-run a source audit for `git2::`, imported/aliased `Repository`, `RepoBuilder`,
  `Submodule::open`, and raw libgit2 calls across `src` and production workspace
  crates. Save the reviewed inventory. New direct repository constructors must
  go through the guard; one passing no-op smoke test cannot establish coverage.

After correctness validation, compare Cargo-only Ir for both `check` and
`test --no-run`, plus a workload that actually uses Git to catch moved or
duplicated initialization. Use fresh, quiet native confirmation with at least
30 independent randomized pairs; grouped subruns remain one paired aggregate.
The diagnostic profile's allocator warnings and process-only counters still
apply. No Cargo execution, benchmark, or host-security mutation was performed
for this audit.
