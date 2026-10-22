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
`<profile>/build/registries/<context>` and reusable ThinLTO backend cache entries
under `.ohm-thinlto-cache/<context>/<backend-options>/<object>.cache`.
Private intermediates live under
`target/<profile>/build/workspaces/<workspace>/<context>`, and incremental state
under `target/<profile>/incremental/<workspace>`. Worktree seeding clones private
state from the donor's target into the recipient's target. Removing a worktree
also removes its default target, so this private state needs no global ownership
record or GC pass. Explicit targets outside the checkout need separate cleanup.

On Linux and macOS, `cargo +ohm gc` reclaims these categories from shared
build directories:

* Global registry and ThinLTO contexts from older Ohm releases, immediately after an upgrade,
  even if the old compiler remains installed and was used recently. A concrete
  compiler executable or driver library being removed or replaced also makes its
  context eligible immediately.
* Other tracked compiler contexts that have not been used for at least one hour.
  Private state in existing worktrees is preserved.
* Individual tracked dependency builds that have not been used for at least one
  hour, even while other dependencies keep their compiler context active. Versions,
  feature combinations, profiles, and targets retain their own usage histories.
* Individual ThinLTO backend objects that have not been used for at least one
  hour, even within a context still used by other builds. Abandoned temporary
  entries use the same inactivity threshold.
* Recognized legacy registry namespaces with no context or usage records, and
  private intermediates, incremental state, and scratch files left in the global
  directory by the old layout, including the old flat ThinLTO namespaces. These
  are eligible immediately, regardless of age
  or whether the original worktree still exists. A colocated target's private
  state is preserved.

A build context groups artifacts that share a compiler, build tools, and relevant
configuration and environment. Multiple projects, crate versions, and feature
combinations can share one context. A dependency build remains reusable while any
project uses it. After removing or updating a dependency, its old build becomes
eligible once it has gone unused for an hour; using other dependencies in the same
context does not extend that deadline. Cargo removes the complete build directory,
including its fingerprints and build-script state, and rebuilds it on demand.

Compiler identity already partitions the cache. The context record also captures
the installed Ohm release. GC compares it with the selected compiler's Ohm release. Older records
can use the installation's `.ohm-version` marker while that compiler is still
installed. Unknown releases are not assumed obsolete, and selecting an older
Ohm release does not immediately evict newer releases' contexts.

Older releases have no grace period. After upgrading, explicitly running `cargo +ohm gc`
can reclaim the previous release's global registry and ThinLTO contexts immediately; an
upgrade does not invoke GC automatically. The one-hour inactivity rule still
applies to the current release's contexts. Legacy namespaces without records are
also discarded immediately, even if their artifacts could still be reused.
They rebuild on demand if needed again.

Ohm keeps compiler provenance, context activity, and dependency activity in one
SQLite database at `.ohm-gc-v1/cache.sqlite` inside each shared build root. Each
compiled dependency variant has one row, shared by all worktrees that use it.
Builds check last use at start and completion, including fresh transitive
dependencies, cache hits, and failures. Like Cargo's downloaded-source tracker,
timestamps use a five-minute update resolution. Ohm rounds use upward, so an entry
always gets a full hour of inactivity before eviction and may remain for up to
five additional minutes. Repeated warm builds within that interval only read the
database; new dependencies and elapsed intervals are recorded in one transaction.
Short builds skip the completion query entirely. No artifact scan or
per-worktree ownership record is needed. The database uses Cargo's existing
SQLite dependency and migration helpers; it has the shared root's locking scope,
independent of Cargo's downloaded-source cache. SQLite uses write-ahead logging
with automatic size-based checkpoints, so warm builds do not force each timestamp
update to durable storage. Transactions remain atomic; after a machine crash,
some recent cache-usage timestamps may be lost, as with the old unsynced file
markers. This can cause reusable artifacts to be reclaimed and rebuilt.

ThinLTO reuses the same SQLite compiler record and active-build lease. Rustc
already refreshes an object's filesystem modification time on a cache hit, so
objects need no additional database rows or per-build bookkeeping. Explicit GC
scans these timestamps outside build locks and rechecks them before retirement.
Fresh builds that do not invoke the backend do not count as use of these optional
objects; removing them does not invalidate existing compiled artifacts. Shared
ThinLTO caches no longer run a directory scan or size-based prune after a build.
If compiler provenance cannot be recorded, new ThinLTO state stays in the
workspace's private build directory instead.
The new context directory preserves reuse across compatible worktrees. Existing
flat ThinLTO namespaces are not imported; they are legacy data for manual GC.

Explicit GC queries expired entries, scans outside build locks, and rechecks their
usage before bounded retirement. Rows are removed with their artifacts, including
all dependency rows when their compiler context is retired. Importing a worktree
snapshot conservatively refreshes the entire context's dependencies for one hour
because an import does not resolve a build graph.

Earlier file-based context records remain readable for cleanup. New builds write
only the database; legacy dependency-set files disappear when their context is
retired. Missing or unfamiliar usage never proves inactivity, and an unreadable
or newer-format database stops collection of that root. Individual entries without
usage history are preserved until used by a tracking build or until their entire
context is reclaimed. Dry runs open the database read-only.
Cleanup runs only when you explicitly invoke `cargo +ohm gc`; builds, tests,
worktree commands, and upgrades do not trigger it.

Cleanup skips contexts that are in use and continues reclaiming unrelated
contexts. Builds, tests, and programs launched by this version of Cargo retain a
shared lease on their compiler context for their lifetime, including after Cargo
exits. A running program therefore does not prevent cleanup of obsolete compiler
contexts elsewhere in the same shared directory. Dependencies and ThinLTO objects
within an actively leased context remain protected. GC reports each busy context
alongside the files and bytes it reclaimed; already-retired trash can be removed
even while a context is busy.

New contexts use a `v2-` namespace and a versioned provenance record so older
collectors preserve them. Existing caches remain eligible under their original
root and profile locks: an older build can still postpone legacy cleanup, without
blocking cleanup of unused `v2-` contexts. Older Cargo versions may only hold
compilation locks, so their running programs do not have the same protection.
Context lock files have stable names outside artifact directories and remain
after collection; they need no timestamp updates or per-build records.
Recognized contexts without usage records are reclaimable under the same locks,
including when a build could not enroll its new context in the database.

`cargo clean` cleans the current workspace's target, including private
intermediates and incremental state. A target-local lock prevents cleaning state
still used by its builds or launched programs, without blocking other worktrees.
The tiny `.ohm-build-lock` and `CACHEDIR.TAG` files remain after a full clean.
Shared registry and ThinLTO artifacts and legacy global state are left for `cargo +ohm gc`.
The first build after switching to this layout rebuilds private intermediates;
existing global registry artifacts remain reusable.

`cargo +ohm gc` performs global maintenance across registered shared build roots.
It also discovers marked legacy roots in the configured build directory and up
to four directory levels beneath `$HOME/.cache`, `$XDG_CACHE_HOME`, and, on macOS,
`$HOME/Library/Caches`. Discovery does not follow directory symlinks or descend
into build profiles. Roots elsewhere can be selected with `--build-dir`; an
actual collection registers them for subsequent runs. Dry runs do not enroll
roots or create metadata. The command can run from any directory, without a
Cargo workspace:

```console
cargo +ohm gc --dry-run
cargo +ohm gc
```

To select one root explicitly, add `--build-dir /path/to/shared-build`.
`--dry-run` lists eligible contexts and legacy workspaces, estimates their file
and byte totals, and leaves artifacts and records unchanged. For example:

```text
Would remove context 6f4e82a9c1d037ab (from ohm-1.98.1-1; current is ohm-1.98.1-2)
     Summary 1248 files, 842.6MiB total
warning: no files deleted due to --dry-run
```

The preview includes all eligible artifacts and files left by interrupted
cleanup, without holding build locks while counting them. Actual collection
reports `Removing` and `Removed`, counts files as it deletes them, and uses small
batches to yield to active builds. Counts exclude GC bookkeeping; like
`cargo clean`, byte totals use file lengths rather than physical disk usage.
Concurrent builds or cleanup can change the preview's estimate.
One invocation keeps draining productive batches until cleanup finishes; there
is no overall time limit. Busy contexts and paths that cannot be safely removed
are reported with a reason. Use `cargo +ohm gc -v` to see the exact lock file.
For example, `lsof /path/to/debug/.cargo-build-lock` shows which processes
have that file open. When the usage database has another writer, GC can still
remove eligible ThinLTO objects and legacy workspace files under their file locks.
If GC encounters a permission error or an unreadable database, it finishes
independent work, prints the totals, and exits with an error listing the affected
paths. `--quiet` suppresses routine output.

Cleanup only removes recognized namespaces inside marked shared build roots.
It preserves external targets, ordinary checkout targets, unknown directory
shapes, and downloaded sources in `CARGO_HOME`. ThinLTO caches in private build
directories retain their separate size and age policy and are removed by
`cargo clean`. This command does not apply a disk-size limit to active shared
build caches.

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
