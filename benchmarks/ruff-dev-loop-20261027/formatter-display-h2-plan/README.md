# Two observable formatter string edits on the released Linux compiler

This unscored experiment uses the complete `crates/ruff_formatter/src/diagnostics.rs` file from Ruff change `2b1d3c60fa`. The larger commit changed 32 files. The selected file changed exactly two four-byte names in `Display` diagnostics. Each selected Cargo command starts in an independently empty, unspaced target and shared build directory. The source checkout is read-only. A private mount supplies the current, genuinely rewritten file. The registered sequence contains a cold build, two unchanged runs, the historical edit, an unchanged build, restoration and a final unchanged build. The production command builds the Ruff CLI. The other command compiles the Python formatter package tests with `--no-run`.

A fresh external Rust executable must report both diagnostic messages from its own Cargo-produced formatter library. Other checks run Ruff's real Python formatter or list its unit-test harness. The runner keeps each Cargo JSON stream, digest and stat identity of every workspace product, physical process records, and unmodified exec traces in the specified scratch directory. There are no timed trials in this screen. [Original Ruff change](https://github.com/astral-sh/ruff/commit/2b1d3c60faafcedc79423661884331eb8834fab7) · [Linux SDK](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-17)

On x86-64 Linux the run requires Python 3.11 or newer, Linux user namespaces, bubblewrap, strace, rustup proxies, a clean Ruff checkout at `93526150df`, the unpacked Ohm SDK and a Cargo cache hydrated for the locked dependency graph. The scratch path must be new, outside the source tree, with enough space for a cold build. Use a different scratch path for each mode.

```sh
python3 -B reproduce.py --mode build --ruff /path/to/ruff --sdk /path/to/ohm-17 --cargo-cache /path/to/cargo-home --scratch /path/to/new-build-state
python3 -B reproduce.py --mode test --ruff /path/to/ruff --sdk /path/to/ohm-17 --cargo-cache /path/to/cargo-home --scratch /path/to/new-test-state
```

The pre-run launcher explicitly remounts read-only source, SDK and protocol paths if they live on tmpfs, and writes failure evidence only in a scratch directory that this invocation created. The original registration at `87db5ef2a8209c12da45d4869c531abcd7feb256` preceded this portability correction. Both native histories were still empty.
