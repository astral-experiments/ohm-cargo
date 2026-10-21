# Independent lazy Git review

Reviewed `work/cargo-lazy-git` against pinned Cargo
`5e5d271d763d7beb38b48755e22bd59e93f02b97` on 2026-10-21. The reviewed
implementation modifies 14 files, +143/-3. This review did not build, test,
profile, or change the candidate.

No blocking source-level issue found. The repository-opening entry points in
the main Cargo crate are covered: GitRemote database opens, checkout database
opens and clones, repository recreation/GC, Git registry opens/init, the VCS
utility, cargo fix, and cargo worktree. Submodule opens require an existing
parent repository, so they follow initialization. The xtask and test-support
repository constructors are separate programs/library test support and do not
inherit the Cargo executable's callback.

The ownership policy remains executable-only. Registering the callback does
not initialize libgit2, a library call without registration does not consume the
Once, and all guarded repository operations call the callback before opening a
repository. The callback remains the existing `set_verify_owner_validation(false)`
policy and does not recursively invoke Cargo's Git helpers. The existing library
contract therefore retains libgit2's default owner validation.

The direct openssl-probe dependency is the already locked 0.1.6 version. Its
startup call uses the same target cfg and the same implementation as git2's
deprecated `init_ssl_cert_env_vars` wrapper. Existing valid certificate values
are preserved; invalid or absent values are probed identically. Cargo's context
configuration still occurs before this point. Thus subprocesses retain the
previous certificate environment even if the command never opens Git.

The first asynchronous HTTP client constructs HandleConfiguration before
spawning its worker, and the new guard completes libgit2 initialization there.
Cargo fix has a separate guard before its lock/diagnostic servers, including
the allow-no-vcs path. Gitoxide retry workers already receive a repository that
was opened by a guarded entry point. Compilation workers start after dependency
resolution. The tracing/build-analysis writer threads serialize owned data and
do not read process environment variables in their worker loops.

Two constructors can initialize libgit2 without the new callback:
`Config::open_default` in proxy lookup and `Oid::from_str` in revision parsing.
Neither opens a repository. The normal Cargo call paths run before compilation
workers or after the explicit HTTP/fix guards. Config initialization within
fetch_with_libgit2 already receives an existing guarded repository. The OID
constructor in GitSource::new can precede its database open, but the owner policy
is still applied before that later open. These do not expose a missed ownership
boundary in the current implementation.

The curl workaround now checks the affected curl-version prefixes and whether
multiplexing was explicitly configured before asking for a proxy. That retains
the condition for disabling multiplexing while avoiding an otherwise discarded
Git config lookup on modern curl. Git proxy lookup errors were already ignored,
so their skipped evaluation does not suppress a reported error. The default
libgit2 HTTPS transport and existing custom git2-curl registration condition
remain unchanged.

Validation still required before claiming correctness/performance:

- Separate-process tests for default library owner validation and the Cargo
  executable's existing owner policy, avoiding process-global contamination.
- Child environment comparison with SSL_CERT_FILE and SSL_CERT_DIR unset, valid,
  and invalid, including a fresh command that never opens Git and a command that
  does. The helper's Once tests alone do not cover this contract.
- Existing Git dependency, cached/offline Git, Git registry, submodule, new/init,
  fix/worktree, default/custom HTTP transport, and SSH host-verification suites.
- Profiling/native confirmation only after the final formatted diff is frozen.

## Recheck with owner-policy coverage

At 03:14 UTC, rechecked diff SHA256
`2e0a634725a7d26728191099059c2ee1db6982b00f6e92d504e55da890e64f90`
(14 files, +294/-4). The implementation guards are unchanged. CLI argument
dispatch now factors into main_with_matches for three separate-process tests.
The extraction preserves the original configure/register/execute ordering.

The tests initialize libgit2 through Config::new before calling the supported
GET_OWNER_VALIDATION option with an int pointer. Each test runs in an isolated
child, and the parent checks a completion marker as well as exit status, avoiding
a false pass when an --exact filter matches nothing. The library test never
registers the executable callback; the two binary tests exercise real callback
registration and init dispatch. These cover owner-policy isolation, not whether
the expensive TLS context itself remains unloaded: the getter intentionally
initializes libgit2 first. The profiling experiment covers the latter contract.

Removing `test = false` enables the Cargo executable's unit-test target by
default. This is an intentional Cargo-repository test-scope change; it does not
alter uv's test-build workload. No new blocking source issue found. Runtime
execution and certificate-environment validation remain pending.

At 03:24 UTC, the parent reported a compiler error missed by the source review:
`std::sync::Once` does not implement `Default`, so the helper's derived
implementation cannot compile. The staged production build is held before any
lazy-Git compilation. The author is replacing the derive with an explicit const
constructor; the revised frozen patch requires a recheck before that build.

At 03:26 UTC, rechecked revised patch SHA256
`3707975b6b134ecce3c811963ffe65a96c1c564e9000ae4255d1bdd56cb76deb`.
Only `src/util/git.rs` changed: a private const constructor initializes the same
`OnceLock::new()` and `Once::new()` fields, and both the static and isolated
tests use it. This removes the invalid trait requirement without changing
registration, initialization, or threading behavior. All 14 frozen file hashes
match the independently assembled PR175-plus-lazy-Git tree
`c692e3c07d295e596b9f10eb4b1c89bb498caf68`. Runtime validation is still pending.

At 03:35 UTC, the parent reported successful execution of 8 unit tests, 23
focused integration cases, both Docker HTTPS rejection/custom-CA tests, and all
12 SSL child-environment comparisons on this unchanged corrected source. The
separate production-settings build accepted the same complete source tree and
frozen file hashes before invoking Cargo at 03:34:18 UTC. No benchmarks are run
by this audit/build agent.
