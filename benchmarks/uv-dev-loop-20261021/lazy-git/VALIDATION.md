# Correctness scope and retained attempts

All successful correctness runs used the final corrected source tree
`c692e3c07d295e596b9f10eb4b1c89bb498caf68` and candidate patch SHA256
`3707975b6b134ecce3c811963ffe65a96c1c564e9000ae4255d1bdd56cb76deb`.
The final summary and every command/log are preserved. Historical source-review
notes and patch metadata predate execution and retain their original pending
wording; the completed reports govern the result.

The focused Rust coverage passed 8 unit tests and 25 integration tests. Unit
coverage includes isolated helper registration/once behavior, separate-process
library ownership validation, the real Cargo CLI registration/first-repository
entry path, and the existing curl multiplexing compatibility test. The owner
getter initializes libgit2 using its supported API first and uses the already
locked dev-only libgit2-sys edge for its named GET_OWNER_VALIDATION option.
No privileged ownership change or global Git configuration was used.

Integration coverage includes local and cached Git dependencies, submodules,
git2/gitoxide fetch paths, corrupted-checkout recovery, Git and HTTP registries,
init/autodiscovery, fix, worktree, HTTP/HTTPS authentication and SSH behavior.
Two existing Docker HTTPS tests verify rejection of an untrusted self-signed
certificate and success with the custom CA. Docker used only the local Unix
socket; certificate verification remained enabled. No successful explicit
proxy CONNECT fixture was available in the inspected suite. Cross-platform CI
and additional profile/build-analysis logging permutations have not run.

The compiled test harness invoked Cargo hash
`b70f184bf9ed5da7363bcc99b849a9890a8ac2382092071e1792e3380882c32c`.
The SSL child-environment matrix directly invoked the frozen normal candidate
hash `52d733d6395ab7c0043b6d45f47c8138eab6f9c3570bbdcb312dcdecba2f68a1`.
These have the same final source tree but different build features/profiles
from the measured all-static/ohm-defaults production candidate
`b54037b8f4041b7add52dcc9ad86357e7d8a86953a35c64e3d76718b0fed7cfd`.
The 33 tests and SSL matrix were not rerun against that exact production CLI.
Its source/build/strip checks and both variants' fresh Ohm-enabled uv check and
test-build preflights passed. This distinction is a validation limitation.

The 12 SSL child-process cases cover unset, valid custom and invalid
SSL_CERT_FILE/SSL_CERT_DIR paths through both a build script and an actual
external Cargo subcommand, for baseline and candidate. Both variants produced
identical captures. Valid values remained unchanged; absent/invalid paths had
the same existing system-probe fallback. Fixture sources, captures, logs and
the public trust bundle are retained. Compiled fixture targets and Cargo cache
databases are intentionally excluded from the archive.

Two failed attempts remain visible:

1. The first normal source build used a derived Default implementation for
   std::sync::Once, which does not compile. An explicit const constructor fixed
   it before the final source was frozen or production compilation began. The
   superseded patch, failed build metadata and compiler log are historical
   artifacts, not the measured candidate.
2. The first init UI snapshot failed because the runner inherited
   CARGO_TERM_COLOR=never. Removing inherited color/hyperlink variables let the
   same compiled test and Cargo binaries pass the remaining 15 integration
   cases. No Rust source or expected snapshot changed. Both complete reports
   and the initial failing log are retained.

For focused reproduction, build the final candidate's tests with stock Rust
1.99.0 in a separate, quiet correctness phase after freezing benchmark
binaries. Use the original normal-build environment recorded in
`validation/normal-builds/`, and clear inherited CARGO_TERM_COLOR and
CARGO_TERM_HYPERLINKS. Set CARGO_CONTAINER_TESTS=1 before compiling the test
macro/harness if running the HTTPS cases. Direct Docker only to the local
Unix socket and check for conflicting cargo_test_ containers first.

```sh
cargo +1.99.0 test --release --locked -p cargo --lib --bin cargo --test testsuite --no-run
cargo +1.99.0 test --release --locked -p cargo --lib util::git::tests:: -- --nocapture --test-threads=1
cargo +1.99.0 test --release --locked -p cargo --bin cargo -- --nocapture --test-threads=1
cargo +1.99.0 test --release --locked -p cargo --lib context::tests::disables_multiplexing -- --exact --nocapture --test-threads=1
cargo +1.99.0 test --release --locked -p cargo --test testsuite EXACT_TEST_NAME -- --exact --nocapture --test-threads=1
```

The report's full command arrays and named cases are authoritative; require a
nonzero matching test count as well as exit status. A copied prebuilt test
binary retains its baked Cargo path. Rebuild it at a new prefix rather than
assuming copying rebases that path. The archived orchestration/resume helpers
record the original workspace layout and frozen artifacts; they are not a
portable substitute for a fresh local test build.

The standalone SSL comparison helper can run at any prefix:

```sh
python3 harness/validate_ssl_environment.py \
  --baseline BASELINE_CARGO --candidate CANDIDATE_CARGO --rustc PINNED_OHM_RUSTC \
  --cert-file /etc/ssl/certs/ca-certificates.crt --cert-dir /usr/lib/ssl/certs \
  --output NEW_SSL_RESULTS
```

It makes six small dependency-free builds and invokes six external Cargo
subcommands. Run it outside performance measurement. It does not alter uv or
disable verification. Record which actual baseline/candidate binaries were
used rather than conflating source-equivalent and byte-identical coverage.
