# Lockfile rereads on a workspace resolve cache miss

Two private Linux x86-64 release-profile PGO Cargo binaries ran the same eleven native commands. Both reported the same complete Cargo version. The candidate reuses a decoded TOML document when the ordinary second shared read of `Cargo.lock` yields exactly the same bytes. It still reconstructs the dependency graph from the current workspace.

The measured parent was `2fe90823d8`. The candidate was `0e398aa5aa`. Its Git parent `9d675d9393` differs from the measured parent only in `tests/testsuite/freshness.rs`. Both binaries used the same rustc `ca780121c` for these checks. The binary SHA-256 values, source trees, PGO profile, build-receipt digests and fixture compiler identity are in `subjects.json`. [Parent Cargo source](https://github.com/astral-sh/ohm-cargo/tree/2fe90823d8eadc95de56c2cde8d41e0082aac0eb) · [Candidate Cargo source](https://github.com/astral-sh/ohm-cargo/tree/0e398aa5aa13fa8b88b59c965d229923e53ab8cd).

## Native results

The workspace member depends on an excluded local package named `bridge`. Its own path dependency named `late` lives outside the workspace. Cargo discovers that external package while it converts a parsed lockfile into a dependency graph. A writer blocks on a FIFO in place of the resolve-cache marker. When Cargo reads the marker after its first graph conversion, the writer installs the external manifest or a replacement lockfile before allowing Cargo to continue. All files, links, caches and FIFOs used by the fixture are private to an independent invocation.

| Case | Observed on each Cargo |
| --- | --- |
| Valid lock, external manifest appears | Cargo read the same 300 bytes twice under distinct shared locks. The first open of the external manifest returned `ENOENT`. The next succeeded. The reported edges were `member → bridge → late`, equal to the independently present-path result. |
| Valid TOML, invalid external version | The two 308-byte reads were identical. The first conversion skipped the absent path. The second discovered it and rejected `not-a-version` with exit 101 and the ordinary invalid-major-version diagnostic. The static present-path control produced the same stderr diagnostic. |
| Malformed first read, no FIFO writer | Cargo returned 101 on the first 12 bytes, with a TOML error at line 1, column 12. The marker and external manifest had zero opens. A cache-disabled control produced the same diagnostic. |
| Same-length, backdated replacement during the marker read | The old and new 300-byte lockfiles shared their mtime but had different inodes and contents. The two shared reads captured their distinct hashes. The raced and independently static replacement both returned 101 with identical complete stderr. |
| Recovery and unchanged repeat | Restoring the valid input recovered both graph edges. The following command reported a resolve-cache hit and read the lockfile under one shared lock. |

`observations.json.gz` contains the two 11-command rosters, the literal read payloads and ordered native syscalls on the lockfile, marker and external manifest. It also includes the successful process argv, the returned package graph or error, and digests of complete retained traces and streams. The projection gives each of the three paths a role and drops unrelated calls and wall-clock timestamps. The original fixture's two repeated-source comparisons preserve physical file identity. The first nine diagnostic commands enabled the workspace cache and Cargo's resolver logging, except for explicitly cache-disabled oracle commands. The two replacement commands used ordinary stderr. All commands after initial generation used `--locked --offline`.

## Verify the recorded result

Run from this directory with Python 3.11 or later on any platform.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
```

## Reproduce one arm on Linux

Supply an Ohm Cargo executable that supports the workspace resolve cache, a compatible Ohm SDK directory containing `bin/rustc` and `lib`, and installed rustup proxies. Linux `strace` with child tracing and descriptor paths must be available to the current user. The fixture uses only local packages. Each run needs a new output directory and at least 16 MiB of free space. The recorded run also required 45 GiB free on its home filesystem and 40 GiB on its secondary filesystem.

```sh
study=$(mktemp -d)
python3 -IB reproduce.py --cargo "$CARGO_BINARY" --sdk "$RUST_SDK" --output "$study/arm"
```

Use `--expect-sha256` to require an exact Cargo image. The script finds `cargo` and `rustc` rustup proxies in `$HOME/.cargo/bin` by default. Set `RUSTUP_PROXY_DIR` to use another proxy directory. The private rustup home routes `cargo +ohm` through the supplied executable. The command leaves full traces, stdout, stderr, writer receipts and a path-free projection in the output directory. The public replay command was also run from fresh directories with both enrolled executables. Those separate eleven-command replays are bound in `fresh-replays.json`.

These controls exercise file locking, graph construction and diagnostics. Measuring the number of TOML deserializations or elapsed time requires separate instrumentation.
