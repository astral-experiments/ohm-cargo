# Incremental session input validation

Session validation still compares the values of recorded filesystem queries.
A Linux session can reuse successful directory listings, compiler and loader
library traversal results, and canonical paths. It continues to read exact file
bytes and poll artifact identity metadata during every validation.

## Coverage and synchronization

The cache uses nonblocking inotify directory watches with no background thread.
Each validation checks mount topology and drains notifications before evaluating
inputs, then repeats those checks before accepting its results. A notification
that affects any reused or newly cached topology discards the pass and evaluates
all inputs through the original polling implementation.

A cached result carries watches for directory membership or specific ancestor
entries, along with the device, inode, type, permissions, owner, and group of the
path components. Symlink targets are checked explicitly, including intermediate
links that canonicalization would otherwise hide. These structural observations
are polled once per path in each validation. Unrelated sibling entries do not
invalidate a named ancestor watch.

Watches are registered against an opened directory descriptor, and their device
and inode are checked before an existing path registration can be reused. This
keeps registration tied to the observed directory when its path is replaced.
Failed queries use their original polling operation without opening each
ancestor. Successful directory listings and canonicalizations are repeated after
coverage is armed. Tree traversal first identifies every visited directory, then
repeats the scan after installing coverage; a different directory set prevents
cache admission. Empty directories are included in watch coverage even when they
contribute no library identities.

Queue overflow, removed watches, and mount changes retire the watcher generation.
An initialization, registration, or read failure disables it for that preparation.
The corresponding filesystem queries continue by polling. Starting a new
preparation drops the old cache and its watches.

## Scope

- The watcher accepts ext4, XFS, Btrfs, and tmpfs directories. Every path component
  must have supported coverage. Network, FUSE, overlay, pseudo, and unknown
  filesystems use polling.
- Other operating systems retain the original polling implementation.
- File contents always use fresh byte reads. Artifact identities retain their
  existing metadata and canonical-path fields; their metadata is polled even
  while a traversal result is reused.
- General globs, same-file checks, negative or failed topology queries, and
  paths containing `..` remain polled. Coverage removes `.` and redundant
  separators so a final symlink stays visible, while the authoritative query
  retains its original path spelling. Related metadata queries share
  observations only within one validation.
- Cargo-authored input files still publish their exact bytes through the existing
  graph API. Notifications do not update dependency values or clear conflicts.

This does not create an atomic filesystem snapshot. A concurrent change can race
an ordinary filesystem read, as it could before caching; the existing validations
before and after prepared execution remain in place. Notifications are used only
for topology whose coverage can be checked. In particular, inotify does not
report every memory-mapped file modification, so a quiet queue never substitutes
for reading an input file. See the [inotify manual](https://www.man7.org/linux/man-pages/man7/inotify.7.html)
and [kernel inotify documentation](https://www.kernel.org/doc/html/latest/filesystems/inotify.html).

## Focused verification

The session-input tests compare cache-backed validation with the original polling
queries. They cover unchanged tree reuse, new subdirectories during setup,
changes at the final synchronization boundary, overflow and backend failure,
ancestor and symlink replacement (including trailing `.` and separators),
negative queries without watch setup, replaced watch registrations, metadata
changes with notifications deliberately discarded, and memory-mapped byte writes.
Test-only counters establish that an unchanged pass skips traversal and
canonicalization while retaining identity metadata reads.


## Measured comparison

The release build, all 22 session-input unit tests, all 38 session integration
tests, and formatting pass. On Linux x86_64, 30 alternating parent/current pairs
following real leaf edits in a 101-crate path workspace produced these medians:

| Compiler | Parent client | Watcher client | Parent server | Watcher server | Client speedup |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ohm 1.98.0-2 | 116.04 ms | 110.90 ms | 106.62 ms | 101.89 ms | 1.046x |
| Stable Rust 1.97.1 | 107.81 ms | 105.09 ms | 97.34 ms | 95.05 ms | 1.026x |

Both sides retained one preparation across 31 checks, with a changed leaf
dep-info artifact after every measured edit. They used the same compiler and
independently warmed outputs. Startup and cold checks are recorded separately.
The [Ohm data](benches/session/results/watchers-ohm-linux-x86_64.json) and
[stable data](benches/session/results/watchers-stable-linux-x86_64.json) contain
all samples, binary hashes, compiler versions, and counters. Reproduce with
`benches/session_compare.py --before PARENT_CARGO --after WATCHER_CARGO
--crates 100 --rounds 30`, selecting the compiler with `RUSTUP_TOOLCHAIN` or
`--rustc`.

The archived initial [Ohm](benches/session/results/watchers-initial-ohm-linux-x86_64.json)
and [stable](benches/session/results/watchers-initial-stable-linux-x86_64.json)
runs showed a regression to about 203 ms per check. Setting up ancestor watches
for absent implicit target directories dominated that implementation. Failed
queries now return before coverage setup; a regression test verifies that these
queries create no watches. Lookup-only caches use FxHashMap with raw query path
spellings, while filesystem coverage checks remain in place. These measurements
support a modest end-to-end improvement, with file polling and other Cargo work
still present.
