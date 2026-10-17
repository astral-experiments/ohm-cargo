# Ohm Cargo

An experimental fork of [Cargo](https://github.com/rust-lang/cargo), Rust's package manager and
build tool, for [Ohm](https://github.com/astral-sh/ohm): a Rust toolchain designed for fast, highly
parallel local development.

**Warning:** Ohm includes backported and experimental optimizations that may be unsound. All Ohm
code changes, PR summaries, and additional documentation were authored entirely by GPT-6 Astra in
Codex.

Use Ohm only for local development, and at your own risk. Never use it for production builds or
releases, and always verify your work with the official Rust toolchain.

Ohm defaults enable native ThinLTO object caching for supported Linux builds. Cargo manages
`<build-dir>/.ohm-thinlto-cache`, pruning it after builds to 2 GiB or 100,000 objects and expiring
entries unused for 30 days. Concurrent builds can temporarily exceed these limits. Compiler
wrappers, unsupported compilers, and unsupported backend configurations retain normal compilation.
Optimization settings, including the selected LTO mode, are preserved.

Use `cargo +ohm -Zohm-thinlto-cache=no build --release` to disable automatic caching, or
`-Zohm-defaults=no` to disable all Ohm defaults. `[unstable] ohm-thinlto-cache = false` provides the
same targeted opt-out in Cargo configuration. An explicit rustc `-Zthinlto-cache=PATH` keeps its own
directory and eviction policy.

## Shared frontend stages

Ohm defaults enable frontend query reuse for compatible debug checks and builds
with a supporting compiler:

```sh
cargo +ohm check
cargo +ohm build
```

Cargo preserves separate checked and built artifacts while giving compatible
units the same compiler identity and incremental directory. Source, feature,
profile, dependency, and build-script inputs remain tracked. Reuse excludes release and test targets, procedural macros, build scripts,
explicit codegen backends, and workspace compiler wrappers. It falls back to
ordinary compilation when the compiler does not support the experiment.

Use `-Zohm-shared-stages=no` on both commands to opt out, or set
`[unstable] ohm-shared-stages = false` in Cargo configuration. `-Zohm-defaults=no`
also disables automatic stage sharing; an explicit `-Zohm-shared-stages` enables
it independently of the other Ohm defaults.

The first native build can reuse frontend results from a preceding check. Once a
native build exists, subsequent builds restore its saved graph and query cache;
checks restore their own saved state and retain the native work products. Both
paths apply normal incremental validation to changed inputs. Each incremental
session retains at most one checkpoint per stage, removed with the normal build
cache. This uses additional cache space.

## Reusing native integration tests during checks

Ohm defaults let `cargo check --test <name>` reuse a compatible native integration-test
compilation. The check replays its warnings and reports ordinary metadata-only
artifacts. It does not run the test executable.

Reuse requires a standard test harness, a matching debug profile, fresh native
artifacts and build-script execution records, and authenticated compiler diagnostics.
The existing procedural-macro trust policy still applies. Missing or stale records,
compiler wrappers, and unsupported configurations fall back to ordinary checking;
that fallback does not build the package binaries required by native tests.
Explicit compiler-output options and user-supplied unstable Rust flags also use
ordinary checking.

Older native builds without a diagnostic record cannot supply this reuse. Use
`-Zohm-defaults=no` to disable the automatic optimization.

## Early integration-test compilation

Ohm defaults start supported first native integration-test compilations alongside
the package library. This helps CLI tests that invoke the package binary without
linking its library. All other compilation dependencies remain prerequisites;
Cargo still builds the library and binaries before running any tests. Existing
test executables retain the normal incremental and relink paths.

The compiler command and optimization settings are unchanged. Cargo accepts an
early result only when that invocation succeeds, consistently reports the package
library unused, and the library finishes successfully, including Cargo's warning
policy. Otherwise Cargo discards provisional diagnostics and retries after the
library succeeds. Diagnostic buffering is bounded; overflow also retries through
the normal streaming path. A failed library still fails the command.

This requires at least two jobs, Ohm defaults and headstart, and a compiler that
supports transparent unused-extern reporting. Custom linker inputs, native-link
build-script outputs, artifact dependencies, and indirect linkage of the package
library retain ordinary scheduling. No prior `cargo check` is required, and check
scheduling is unchanged.

Use `cargo +ohm -Zohm-early-tests=no test` to opt out, or set
`[unstable] ohm-early-tests = false` in Cargo configuration. The explicit override
is inherited by external Cargo subcommands. `-Zohm-defaults=no` also disables it.

## Unused development dependencies in targeted tests

Ohm defaults can skip previously unused workspace dev dependencies when rebuilding
one native library test target, for example `cargo +ohm test -p app --lib selected`.
This avoids paths such as compiling the ordinary library solely to build a test
helper that the unit-test executable never uses. Feature resolution, compiler
arguments, and optimization settings retain the complete dependency graph.

These targeted rebuilds validate the code their executable uses. Errors and
warnings inside skipped dependencies are not reported. Disable deferral when
validating the complete declared dependency graph.

A previous executable's unused-dependency report only permits an attempt. Cargo
accepts the new executable after its successful compiler invocation proves every
deferred dependency unused. Missing or inconsistent proof, new dependency usage,
or compiler diagnostics discard the provisional output and retry once with the
complete graph. Interruption and compiler launch failures stop the command.

Initial builds, up-to-date and dependency-only builds, multiple test targets,
explicit targets, and unsupported compilers use ordinary scheduling. Build
scripts, proc macros, native links, artifact dependencies, and opaque linker
inputs in the skipped closure also prevent deferral. A discarded attempt can add
compilation work.

Cargo revalidates retained build-script outputs before invoking the test
compiler. On Linux, dependency scripts may contribute ordinary static archives
and ELF objects through native search directories inside their own `OUT_DIR`.
Those dependencies still build normally. Root-package native inputs, opaque
linker arguments, external search directories, and unsupported files retry the
complete graph and prevent recording unused-dependency evidence. Configuration
and environment outputs alone do not prevent deferral.

Use `cargo +ohm -Zohm-defer-dev-deps=no test -p app --lib` to opt out, or set
`ohm-defer-dev-deps = false` in the `[unstable]` configuration table.
`CARGO_UNSTABLE_OHM_DEFER_DEV_DEPS=false` is the environment equivalent. External
Cargo subcommands inherit explicit overrides. `-Zohm-defaults=no` disables the
optimization with the other Ohm defaults.

## License

Cargo is primarily distributed under the terms of both the MIT license
and the Apache License (Version 2.0).

See [LICENSE-APACHE](LICENSE-APACHE) and [LICENSE-MIT](LICENSE-MIT) for details.

### Third party software

This product includes software developed by the OpenSSL Project
for use in the OpenSSL Toolkit (https://www.openssl.org/).

In binary form, this product includes software that is licensed under the
terms of the GNU General Public License, version 2, with a linking exception,
which can be obtained from the [upstream repository][1].

See [LICENSE-THIRD-PARTY](LICENSE-THIRD-PARTY) for details.

[1]: https://github.com/libgit2/libgit2

