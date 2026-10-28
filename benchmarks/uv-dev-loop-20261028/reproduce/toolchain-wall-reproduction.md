# Edited full-workspace timing

The two cohorts compare the matched Cargo and Wild binaries after a private-body source edit on uv `c22e6b71933443e9cd299d4b6ac8de035ed4825b`. Both arms compile uv with the same released Ohm 1.99.0-17 rustc. The candidate Cargo binary includes the five Cargo changes and the guarded standard-library path comparison. Each measurement includes Cargo, all compiler and linker children, and process launch and exit.

`toolchain-wall-plan.json` freezes two cohorts of eight order-balanced, shuffled pairs for each of `check`, `build` and `test --no-run`. The three endpoints are separate full-workspace commands. Each endpoint and cohort has its own private copy of the released toolchain, registry, source archive and target. A baseline build warms the pristine source. Its two arm targets are identical initial copies, each parked between trials so both run at the same visible path. Every pair writes one new string to the shared source file before running both arms and admits the result only if uv recompiles, the two arms report the same checked/compiled packages and test executables, and no test executes.

From the chat workspace, prepare the two cohorts and then seal both before the first timed command.

```sh
sh work/toolchain_wall.sh warm toolchain-wall
sh work/toolchain_wall.sh warm toolchain-wall-replica
sh work/toolchain_wall.sh seal toolchain-wall
sh work/toolchain_wall.sh seal toolchain-wall-replica
```

Each seal verifies the Cargo and Wild ELF hashes and owner, the private released rustc and driver library hashes, the matching Cargo build-audit receipt and the shared release's original linker hash. The snapshot audit checks all relative paths, file sizes, modes, modification times and symlink targets against the seed, along with the Cargo rustc-info cache and pristine input-source hashes. It builds a small Rust program with each Cargo arm under `strace`. The required successful process launches include that private rustc and exactly one linker at its fixed `lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd`. The two `link-probe-*.log` files retain those traces. During timed trials the harness atomically replaces the private Cargo and linker slots with hard links to the selected files, verifies their hashes before starting the clock and records both hashes in the raw CSV. The shared release's linker is checked again when the endpoint ends.

In the reserved quiet window, run these sequentially.

```sh
sh work/toolchain_wall.sh measure toolchain-wall
sh work/toolchain_wall.sh measure toolchain-wall-replica
```

The native metric is elapsed nanoseconds. The report converts it to seconds and computes median paired reductions, exact two-sided sign tests excluding ties and distribution-free median intervals. A claim of faster elapsed time requires a positive median and p < 0.05/3 on the initial cohort, then a positive median and p < 0.05 on the independent repeat.
