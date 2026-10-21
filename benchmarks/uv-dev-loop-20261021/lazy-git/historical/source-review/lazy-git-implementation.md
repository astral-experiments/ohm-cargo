# Deferred Git initialization candidate

Worktree: `work/cargo-lazy-git`, branch `codex/lazy-git-initialization`, based on
`5e5d271d763d7beb38b48755e22bd59e93f02b97`. Source changes are uncommitted for
review. No Cargo builds, tests, or benchmarks were run. All 12 touched Rust files
pass the installed default rustfmt 1.10.0 with edition/style edition 2024, without
formatting changes; stdin mode limited formatting to those files. `git diff
--check` passes. The helper's two unit tests, three isolated CLI policy tests,
and additional existing curl-test cases are written but unexecuted. See
`lazy-git-validation.md` for their design, the prepared SSL environment helper,
and focused existing network coverage. Source inspection confirmed that git2's old
environment initializer delegates to the same unsafe openssl-probe 0.1.6 API
used here. Parsed manifest/lockfile inspection confirms the target-specific
dependency and single Cargo dependency edge reuse the existing package record
without changing its version, checksum, or source.

## Why not disable git2's HTTPS feature

Cargo does not always install git2-curl. `needs_custom_http_transport` returns
true for a proxy, non-default HTTP configuration, or HTTP_TIMEOUT. With default
settings, `init_git_transports` returns without registration; it also returns
when configuration lookup or HTTP-handle creation fails. `fetch` defaults to
`fetch_with_libgit2` unless the external Git CLI or gitoxide fetch is explicitly
selected. Thus normal HTTPS Git fetches rely on libgit2's built-in transport.

Cargo explicitly enables git2's `https` and `ssh` features. git2-curl 0.22 itself
depends on git2 with default features disabled and only registers HTTP/HTTPS
schemes when `register` is called. libgit2-sys has separate `https` and `ssh`
features and no default feature list. Removing git2's `https` feature would
remove a supported network path rather than eliminate redundant initialization.

Always installing git2-curl would be a separate transport migration: its own
documentation notes full-transfer buffering instead of streaming, and Cargo
deliberately uses it conditionally. The gix curl/reqwest feature choice does not
replace the default libgit2 fetch path. Vendored/system libgit2, static linking,
and library users also need their current behavior. This patch leaves all
existing transport features, registration, TLS callbacks, and owner policy
settings unchanged.

## Implemented scope

- The CLI keeps certificate environment probing at its existing initialization
  point, using openssl-probe 0.1.6, already present transitively in the lockfile.
  Platform cfg matches git2's Unix HTTPS probe except macOS/iOS. This preserves
  child SSL_CERT_FILE/SSL_CERT_DIR values, including existing probe behavior for
  valid custom paths and absent/invalid paths.
- The CLI then registers its existing `init_git` function. A library helper
  applies that callback once; unregistered library use remains a no-op and
  never implicitly disables ownership validation. Registration alone does not
  load a TLS context. An unregistered helper call does not consume the Once.
- The helper runs before every production direct repository constructor, with
  shared guards for registry open/init fallback and builder clone. Existing
  parent-repository ancestry covers `Submodule::open`. Test fixture constructors
  and the separate xtask binary remain unchanged.
- The bad-curl workaround checks explicit multiplexing and the existing version
  prefixes before consulting Git proxy configuration. Actual proxy precedence
  and bad-version behavior remain unchanged.
- Two additional boundaries initialize before relevant background work:
  `HandleConfiguration::new` initializes before HTTP clients can start their
  workers, and `cargo fix` initializes before starting fix servers. The latter
  covers `--allow-no-vcs`, which bypasses initial repository discovery.

HTTP-handle preparation can therefore still initialize Git even when the
command has no Git dependency. That retains the current behavior for active
network operations and avoids deferring git2's environment probe into HTTP
workers. The intended saved work is offline/fresh local compilation where no
repository, network handle, or fix worker is needed.

## First-use/thread audit

| Route | First relevant initialization boundary |
| --- | --- |
| Git dependency, cached or fresh | `GitRemote::db_at` or `utils::init` before fetch/checkout. Source futures are `async_trait(?Send)` and driven locally during resolution before the compiler job queue. |
| Git registry | `GitRegistry::repo` before index open/init. Registry futures are also non-Send and locally driven. |
| gix fetch recovery | Parent `git2::Repository` exists before `oxide::with_retry_and_progress` spawns its scoped worker; inner recovery init is guarded as well. |
| New/init and VCS discovery | Synchronous `GitRepo::init`/`discover` helpers before repository access. |
| Worktree | Synchronous discovery after donor workspace load, before the rest of worktree processing. |
| Fix with VCS checks | Discovery happens at the start of `fix`, before its servers. |
| Fix with `--allow-no-vcs` | Explicit initializer before `LockServer::start`, preventing first Git use during later dependency resolution after fix workers start. |
| Sparse registry/API/download HTTP | Explicit initializer in `HandleConfiguration::new` before `http_async::Client::new` spawns its curl worker, including configurations with an explicit proxy that skip Git-config lookup. Synchronous curl handles use this same configuration path. |
| `CARGO_LOG_PROFILE` | The pre-existing tracing-chrome writer can already exist at CLI setup. Its inspected loop only serializes received data and writes its already-open file; it does not access the process environment. |
| `-Zbuild-analysis` | Its file-logger worker can exist before resolution; its inspected loop only serializes owned messages and writes/flushed the open file. It does not access the process environment. |
| Library embedding | No callback is registered by Cargo's library. Its existing libgit2 initialization/ownership behavior and caller threading obligations remain unchanged. |

The certificate probe at CLI setup can write environment variables at the same
point as before. Later git2 initialization normally sees the valid values and
does not call setenv. The explicit HTTP/fix boundaries prevent first Git use
after those workers start, even if a certificate path disappears between probes.
This is a bounded audit of current Cargo code, not a fix for git2's deprecated
environment initializer or arbitrary concurrent environment mutation by library
embedders. New background-worker or repository-entry paths need to retain these
initialization guarantees. The profiling shim and host security configuration
were not changed.

## Validation plan for parent

1. Run locked compilation, then the helper tests and the existing
   `context::tests::disables_multiplexing` test. The new cases cover explicit
   multiplexing=true and version suffixes. Verify no lockfile drift beyond the
   direct openssl-probe dependency edge.
2. In separate fresh processes, assert default library owner validation remains
   enabled and binary policy disables it before repository access. If querying
   `GIT_OPT_GET_OWNER_VALIDATION` directly in a test, first initialize through a
   supported git2 API; never query raw options before initialization.
3. Run existing local Git dependency, offline cached dependency, submodule,
   Git-registry, corrupt-repository recovery, new/init, fix, and worktree tests.
   Include fix with `--allow-no-vcs` plus a Git dependency and gix recovery.
4. Cover HTTPS Git using both default transport and custom proxy/CA config,
   along with SSH known-host behavior. Keep certificate verification enabled.
   Include an explicit proxy so `HandleConfiguration` is exercised without a
   preliminary Git-config lookup.
5. Compare baseline/candidate child environments for unset certificate variables,
   valid custom paths, and invalid paths. Check normal commands, an external
   Cargo subcommand, and build scripts. Repeat relevant initialization smoke
   checks with profile logging and build-analysis logging enabled.
6. Run Callgrind smoke comparisons for fresh `check` and `test --no-run` to verify
   the removed initialization region. Also inspect one real Git operation to
   verify normal TLS initialization still occurs. Preserve the same environment
   and profiler shim. Instruction counts exclude compiler children.
7. Only claim native gains after quiet independent confirmation with at least
   30 randomized paired observations. Grouped repetitions remain one paired
   aggregate; retain every raw subrun. No timing claim has been established by
   this source change alone.
