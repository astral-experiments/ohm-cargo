# Prepared lazy-Git validation

Source review, rustfmt, and Python syntax parsing are complete. No builds, tests,
network requests, containers, or fixture executions ran during instruction
measurements.

## Ownership policy regressions

Three `cli::git_policy_tests` cases live in the actual Cargo executable's unit
test target. Each launches the same executable with one exact test filter in a
fresh process and private Cargo/Git configuration. A completion marker prevents
an empty filter from appearing successful.

- `library_keeps_owner_validation` calls Cargo's public `GitRepo::init` and
  `discover` without registering the binary callback; validation stays enabled.
- `binary_registration_is_lazy_until_repository_access` dispatches the real
  `locate-project` command through the helper shared with `cli::main`. Its real
  binary callback is registered, but validation stays enabled until the first
  Cargo repository API call, after which it is disabled.
- `binary_init_applies_owner_policy` dispatches real `init --vcs git`, checks
  repository creation, and verifies the executable's disabled owner policy.

There is no mock policy callback, product-only test switch, ownership mutation,
or global config edit. Extracting `main_with_matches` permits explicit parsed
CLI arguments while retaining production dispatch and registration. The guards
being the first statement in `GitRepo::init`/`discover` establish ordering before
libgit2 access; same-owner fixtures alone cannot make libgit2 reject a misplaced
owner-policy call.

git2 exposes a setter but no getter. The tests first call supported
`git2::Config::new`, then use `GIT_OPT_GET_OWNER_VALIDATION` through Cargo's
already-existing `libgit2-sys` dependency. Its pinned C implementation accepts
an `int *`; Rust passes `*mut std::ffi::c_int` and checks the result. No FFI
constant is copied and no test dependency or feature is added.

Removing the binary's `test = false` makes normal CI's `cargo test -p cargo`
run these regressions and its two existing CLI parser tests. Explicit
`--bin cargo` also selects the binary regardless of that setting, as confirmed
by `UnitGenerator` using `Target::is_bin` for named bins. Enabling it adds a CLI
test harness build to Ohm's own tests, not to uv workloads.

Focused commands with the parent's selected build toolchain:

```sh
cargo test --locked -p cargo --bin cargo cli::git_policy_tests -- --nocapture
cargo test --locked -p cargo --lib util::git::tests
cargo test --locked -p cargo --lib context::tests::disables_multiplexing
```

## Child certificate environment comparison

`work/benchmark/validate_ssl_environment.py` creates one dependency-free fixture
and a real `cargo-ssl-env-probe` external subcommand. For unset, valid custom,
and nonexistent certificate paths, it captures exact bytes of `SSL_CERT_FILE`
and `SSL_CERT_DIR` in both external subcommands and real build scripts.

Each build gets a separate target directory. Its capture path also participates
in `rerun-if-env-changed`. Absent and empty values are distinguishable. The
custom CA bundle is an unchanged copy of the supplied trust bundle; its custom
directory points to the original certificate directory. Verification stays
enabled and builds run offline. uv is untouched.

The script requires matching baseline/candidate values for both child types,
matching child types within each variant, and exact preservation of valid
custom paths. It retains subprocess logs, raw captures, executable/script
hashes, and a JSON report including failures. It makes no timing claim.

Example after replacing executable placeholders:

```sh
python3 work/benchmark/validate_ssl_environment.py \
  --baseline /absolute/baseline-cargo \
  --candidate /absolute/candidate-cargo \
  --rustc /absolute/pinned-rustc \
  --cert-file /etc/ssl/certs/ca-certificates.crt \
  --cert-dir /usr/lib/ssl/certs \
  --output work/benchmark/results/lazy-git-ssl-environment
```

This runs twelve Cargo processes, including six tiny builds, and must wait until
performance measurements are idle. POSIX is required for the executable Python
subcommand and byte-preserving environment capture. For tracing coverage,
repeat with `CARGO_LOG_PROFILE=true`; that setting is recorded. Additional
global Cargo flags can be passed with `--cargo-arg=...`.

## Existing network coverage

- `https::self_signed_should_fail`: HTTPS Git on the Apache container with
  default settings; built-in libgit2 HTTPS rejects the untrusted certificate.
- `https::self_signed_with_cacert`: the same fixture with explicit `http.cainfo`,
  forcing the custom git2-curl transport and succeeding with verification on.
- `git_auth::https_something_happens`: local malformed TLS handshake; no Docker
  or public network, but only a failure-path smoke test.
- `git_auth::http_auth_offered`: local HTTP authentication callback coverage.
- `git_auth::ssh_something_happens`: local SSH protocol failure-path coverage.
- `https::github_works`: successful public HTTPS Git, gated by
  `CARGO_PUBLIC_NETWORK_TESTS`; optional when container coverage is available.

The first two require `CARGO_CONTAINER_TESTS=1`, Docker, and the existing Apache
image build in `crates/cargo-test-support/containers/apache`. Its repository,
certificate, and Git configuration are confined to the throwaway container.
Without the gate, a passing suite does not establish that these cases ran.

```sh
CARGO_CONTAINER_TESTS=1 cargo test --locked -p cargo --test testsuite https::self_signed_
cargo test --locked -p cargo --test testsuite git_auth::https_something_happens -- --exact
cargo test --locked -p cargo --test testsuite git_auth::http_auth_offered -- --exact
cargo test --locked -p cargo --test testsuite git_auth::ssh_something_happens -- --exact
```

No existing successful explicit proxy/CONNECT integration test was found.
`net_err_suggests_fetch_with_cli` only checks an error suggestion. A small
extension of the CA test could use `http.proxy=""` with a fresh `CARGO_HOME` to
cover explicit proxy configuration bypassing the Git-config lookup, but it
would not exercise a forwarding proxy. Real CONNECT coverage needs an
additional proxy fixture and remains a gap.
