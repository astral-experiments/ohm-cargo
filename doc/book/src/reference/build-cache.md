# Build cache

Cargo stores the output of a build into the "target" and "build" directories. By default,
both directories point to a directory named `target` in the root of your
[*workspace*][def-workspace]. To change the location of the target-dir, you can set the
`CARGO_TARGET_DIR` [environment variable], the [`build.target-dir`] config
value, or the `--target-dir` command-line flag. To change the location of the build-dir, you can set the
`CARGO_BUILD_BUILD_DIR` [environment variable] or the [`build.build-dir`] config value.

Artifacts are split in two categories:
* Final build artifacts
  * Final build artifacts are output meant for end users of Cargo
  * e.g. binaries for bin crates, output of `cargo doc`, Cargo `--timings` reports
  * Stored in the target-dir
* Intermediate build artifacts
  * Intermediate build artifacts are internal to Cargo and the Rust compiler
  * End users will generally not need to interact with intermediate build artifacts
  * Stored in the Cargo build-dir

The directory layout depends on whether or not you are using the `--target`
flag to build for a specific platform. If `--target` is not specified, Cargo
runs in a mode where it builds for the host architecture. The output goes into
the root of the target directory, with each [profile] stored in a separate
subdirectory:

Directory | Description
----------|------------
<code style="white-space: nowrap">target/debug/</code> | Contains output for the `dev` profile.
<code style="white-space: nowrap">target/release/</code> | Contains output for the `release` profile (with the `--release` option).
<code style="white-space: nowrap">target/foo/</code> | Contains build output for the `foo` profile (with the `--profile=foo` option).

For historical reasons, the `dev` and `test` profiles are stored in the
`debug` directory, and the `release` and `bench` profiles are stored in the
`release` directory. User-defined profiles are stored in a directory with the
same name as the profile.

When building for another target with `--target`, the output is placed in a
directory with the name of the [target]:

Directory | Example
----------|--------
<code style="white-space: nowrap">target/&lt;triple&gt;/debug/</code> | <code style="white-space: nowrap">target/thumbv7em-none-eabihf/debug/</code>
<code style="white-space: nowrap">target/&lt;triple&gt;/release/</code> | <code style="white-space: nowrap">target/thumbv7em-none-eabihf/release/</code>

> **Note**: When not using `--target`, this has a consequence that Cargo will
> share your dependencies with build scripts and proc macros. [`RUSTFLAGS`]
> will be shared with every `rustc` invocation. With the `--target` flag,
> build scripts and proc macros are built separately (for the host
> architecture), and do not share `RUSTFLAGS`.

Within the profile directory (such as `debug` or `release`), artifacts are
placed into the following directories:

Directory | Description
----------|------------
<code style="white-space: nowrap">target/debug/</code> | Contains the output of the package being built (the [binary executables] and [library targets]).
<code style="white-space: nowrap">target/debug/examples/</code> | Contains [example targets].

Some commands place their output in dedicated directories in the top level of
the `target` directory:

Directory | Description
----------|------------
<code style="white-space: nowrap">target/doc/</code> | Contains rustdoc documentation ([`cargo doc`]).
<code style="white-space: nowrap">target/package/</code> | Contains the output of the [`cargo package`].

Cargo also creates several other directories and files in the build-dir needed for the build
process. The build-dir layout is considered internal to Cargo, and is subject to
change. Some of these directories are:

Directory | Description
----------|------------
<code style="white-space: nowrap">\<build-dir>/debug/deps/</code> | Dependencies and other artifacts.
<code style="white-space: nowrap">\<build-dir>/debug/incremental/</code> | `rustc` [incremental output], a cache used to speed up subsequent builds.
<code style="white-space: nowrap">\<build-dir>/debug/build/</code> | Output from [build scripts].

## Dep-info files

Next to each compiled artifact is a file called a "dep info" file with a `.d`
suffix. This file is a Makefile-like syntax that indicates all of the file
dependencies required to rebuild the artifact. These are intended to be used
with external build systems so that they can detect if Cargo needs to be
re-executed. The paths in the file are absolute by default. See the
[`build.dep-info-basedir`] config option to use relative paths.

```Makefile
# Example dep-info file found in target/debug/foo.d
/path/to/myproj/target/debug/foo: /path/to/myproj/src/lib.rs /path/to/myproj/src/main.rs
```

## Shared cache

A third party tool, [sccache], can be used to share built dependencies across
different workspaces.

To setup `sccache`, install it with `cargo install sccache` and set
`RUSTC_WRAPPER` environment variable to `sccache` before invoking Cargo. If
you use bash, it makes sense to add `export RUSTC_WRAPPER=sccache` to
`.bashrc`. Alternatively, you can set [`build.rustc-wrapper`] in the [Cargo
configuration][config]. Refer to sccache documentation for more details.

## Ohm shared build cleanup

With a separate `CARGO_BUILD_BUILD_DIR`, Ohm shares compatible registry builds
and keeps each workspace's private state in its own `target` directory. This
includes final outputs, private intermediates, incremental compiler state,
documentation, and test scratch files. An explicit `CARGO_TARGET_DIR` or
`--target-dir` selects the location of all that workspace's private state;
keep it distinct for each worktree.

The global directory holds compatible registry artifacts under
`<profile>/build/registries/<context>` and reusable ThinLTO backend cache entries.
Private intermediates live under
`target/<profile>/build/workspaces/<workspace>/<context>`, and incremental state
under `target/<profile>/incremental/<workspace>`. Worktree seeding clones private
state from the donor's target into the recipient's target. Removing a worktree
also removes its default target, so this private state needs no global ownership
record or GC pass. Explicit targets outside the checkout need separate cleanup.

On Linux and macOS, `cargo +ohm gc` reclaims two kinds of retired state from
registered shared build directories:

* Legacy private build and incremental state left in the global directory by
  earlier Ohm versions, once both the owning linked Git worktree's
  checkout and Git registration have been removed. A moved worktree, a missing
  checkout still registered with Git, or an unavailable filesystem is preserved.
* A build context's global registry and legacy private artifacts, once it has not been used for
  at least one hour, or its concrete compiler executable or driver library has
  been removed or replaced. Inactivity can expire a context even if its compiler
  remains installed. Private state in existing worktrees is preserved. Legacy
  incremental state for an existing workspace is also preserved because it is
  not partitioned by context.

A build context groups artifacts that share a compiler, build tools, and relevant
environment and configuration. Multiple projects, crate versions, and feature
combinations can share one context. Removing a dependency from a lockfile does not
retire its shared artifacts: any use of a context refreshes the whole context.
There is no per-dependency reference counting or age tracking. Ohm's installer
keeps versioned toolchain directories when updating the `ohm` alias. Running
`cargo +ohm gc` after an upgrade can remove tracked old contexts once they have
been unused for an hour, even while those older toolchains remain installed.
Upgrading does not invoke GC automatically, and recently used contexts remain.

There is no grace period: a cleanup pass can reclaim state as soon as it verifies
retirement and acquires the necessary locks. Ohm records each shared context once
and only enrolls workspace ownership when it finds a legacy global namespace.
Fresh builds do not update per-artifact access times or rewrite these records.
A separate empty `.ohm-gc-v1/last-used/<context>` file records context
use through its modification time. Builds refresh it at start and completion,
including cache hits and failures; importing a worktree snapshot also refreshes
its contexts. No artifact scans or usage database are needed on the build path.
Contexts without usage records are not expired by age, and unknown legacy
namespaces are preserved. Using a context with this version starts its tracking.
Cleanup runs only when you explicitly invoke `cargo +ohm gc`; builds, tests,
worktree commands, and upgrades do not trigger it. An evicted context rebuilds
on demand if used again.

Cleanup skips a root while it is in use. Builds, tests, and programs launched by
this version of Cargo retain a shared lease for their lifetime, including after
Cargo exits. Older Cargo versions may only hold compilation locks, so their
running programs do not have the same protection.

`cargo clean` cleans the current workspace's target, including private
intermediates and incremental state. A target-local lock prevents cleaning state
still used by its builds or launched programs, without blocking other worktrees.
The tiny `.ohm-build-lock` and `CACHEDIR.TAG` files remain after a full clean.
Shared registry artifacts and legacy global state are left for `cargo +ohm gc`.
The first build after switching to this layout rebuilds private intermediates;
existing global registry artifacts remain reusable.

`cargo +ohm gc` performs global maintenance across registered shared build roots.
It can run from any directory, without a Cargo workspace:

```console
cargo +ohm gc --dry-run
cargo +ohm gc
```

To select one root explicitly, add `--build-dir /path/to/shared-build`.
`--dry-run` lists eligible contexts and worktrees, estimates their file and byte
totals, and leaves artifacts and ownership records unchanged. For example:

```text
Would remove context 6f4e82a9c1d037ab (unused for at least 1 hour)
     Summary 1248 files, 842.6MiB total
warning: no files deleted due to --dry-run
```

The preview includes all eligible artifacts and files left by interrupted
cleanup, without holding build locks while counting them. Actual collection
reports `Removing` and `Removed`, counts files as it deletes them, and uses small
batches to yield to active builds. Counts exclude GC bookkeeping; like
`cargo clean`, byte totals use file lengths rather than physical disk usage.
Concurrent builds or cleanup can change the preview's estimate.
If a root is busy or work remains after the per-root budget, invoke
`cargo +ohm gc` again to continue. `--quiet` suppresses the output.

Cleanup only removes tracked intermediate state inside shared build roots. It
preserves external target directories, untracked state from older versions,
ordinary checkout targets, and downloaded sources in `CARGO_HOME`. It does not
apply a disk-size limit to the active build cache.

[`RUSTFLAGS`]: ../reference/config.md#buildrustflags
[`build.dep-info-basedir`]: ../reference/config.md#builddep-info-basedir
[`build.rustc-wrapper`]: ../reference/config.md#buildrustc-wrapper
[`build.target-dir`]: ../reference/config.md#buildtarget-dir
[`build.build-dir`]: ../reference/config.md#buildbuild-dir
[`cargo doc`]: ../commands/cargo-doc.md
[`cargo package`]: ../commands/cargo-package.md
[`cargo publish`]: ../commands/cargo-publish.md
[build scripts]: ../reference/build-scripts.md
[config]: ../reference/config.md
[def-workspace]:  ../appendix/glossary.md#workspace  '"workspace" (glossary entry)'
[target]: ../appendix/glossary.md#target '"target" (glossary entry)'
[environment variable]: ../reference/environment-variables.md
[incremental output]: ../reference/profiles.md#incremental
[sccache]: https://github.com/mozilla/sccache
[profile]: ../reference/profiles.md
[binary executables]: ../reference/cargo-targets.md#binaries
[library targets]: ../reference/cargo-targets.md#library
[example targets]: ../reference/cargo-targets.md#examples
