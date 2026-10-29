# Relink manifest writes on the release-profile Cargo

We ran 12 real Cargo builds on Linux across four separate target directories. Each release-profile Cargo ran once with the published Ohm 1.99.0-19 compiler and once with the source-built release candidate compiler. Each history first ran a binary that printed 17, changed it to print 29, then changed it to print 31. Every command exited successfully and ran the expected new binary.

During the second build an ordinary, unprivileged process watched the private target directory with inotify. Immediately after Cargo removed its previous relink manifest the process placed an absolute symlink to a separate file it owned. Parent a8f0c9aa overwrote that file in both compiler configurations. Fixed 5394ce88 retained the original file bytes and inode, replaced the symlink with a regular cache record and built the edited binary. Preinstalling a symlink before the third command also preserved the sentinel on both versions.

Both Cargos used the same release profile, 239 independently checked Rust externs and 335 native linker files, including 326 rlibs. The unwrapped reproducer uses a private workspace and distinct offline Cargo state. The files record the SHA-256 of the original Cargo outputs, both versions of the sentinel, and whether the cache entry remained a symlink. The procedure asserts the sentinel inode on protected cases and actually executes the generated binary in every phase.

Run `python3 -IB verify.py` from this directory to verify the stored records. On Linux, run `python3 -IB reproduce.py /tmp/new-ohm-relink-record --sdk /path/to/toolchain --expect protected` to check the installed fix. Supply a new private directory each time. Use `--expect follows` on the affected toolchain.
