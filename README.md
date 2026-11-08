# Ohm Cargo

An experimental fork of [Cargo](https://github.com/rust-lang/cargo), Rust's package manager and
build tool, for [Ohm](https://github.com/astral-sh/ohm): a Rust toolchain designed for fast, highly
parallel local development.

**Warning:** Ohm includes backported and experimental optimizations that may be unsound. All Ohm
code changes, PR summaries, and additional documentation were authored entirely by GPT-6 Astra in
Codex.

Use Ohm only for local development, and at your own risk. Never use it for production builds or
releases, and always verify your work with the official Rust toolchain.

On native `x86_64-unknown-linux-gnu` development and test builds, Ohm keeps the
`line-tables-only` debug data for Rust libraries in per-object `.dwo` files. This reduces the debug
data the linker processes after an edit. Keep the build directory available to
debuggers when moving a development executable. Set `split-debuginfo = "off"`
in the development profile to embed the debug information in the executable.
When a private build profile contains these files, `cargo worktree add` lets
the recipient rebuild it with its own debug paths. Both worktrees can reuse
immutable registry artifacts in their shared build directory.

In dev-derived profiles, Ohm builds registry and Git procedural macros and their library
dependencies at optimization level 1 with per-crate ThinLTO disabled. Downstream source edits
execute this code during macro expansion. The first build pays the optimization cost, and a
library used by both a macro and a build script may need two compiled copies. The default applies
to profiles with an implicit optimization level or level 1 and an implicit LTO mode or `lto = "off"`.
Matching build and package optimization overrides take precedence. Path dependencies, build scripts, and
their ordinary dependencies keep Cargo's existing profiles.

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

When rebuilding a single library test target, Ohm can skip unused workspace dev
dependencies. For example, `cargo +ohm test -p app --lib selected` can avoid
rebuilding a helper and the ordinary library used only by that helper. Features,
compiler arguments, and optimization settings stay the same.

The current compilation must confirm that the skipped dependencies are unused.
Otherwise, Cargo discards its output and retries once with the complete graph.
Initial builds and unsupported inputs use ordinary scheduling.

Skipped dependencies' errors and warnings are not reported. Use
`cargo +ohm -Zohm-defer-dev-deps=no test -p app --lib` to validate the complete
declared graph. This optimization is enabled by Ohm defaults; see the
[reference](doc/book/src/reference/unstable.md#ohm-defer-dev-deps) for supported
builds, native-input checks, and configuration options.

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

