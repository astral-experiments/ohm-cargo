# Settled Ruff checks with Cargo’s additional short-fingerprint reads

The candidate met the preregistered **3% noninferiority margin** on one Milan host. Across all 32 adjacent pairs, the median relative slowdown was **−0.009%**, with a 95% block-bootstrap interval of **−2.308% to +1.179%**. The upper bound was below 3%. All eight blocks completed in their frozen order, with no replaced or excluded visits. [Prospective protocol, worker and order](https://github.com/astral-sh/ohm-cargo/tree/19ef923d07c6e71e2af6080bdc29e46ca7ee444f/benchmarks/ruff-dev-loop-20261027/rc19-short-fingerprint-milan-noninferiority-plan)

The timed command was `cargo +ohm check --workspace --locked --offline -j8 --message-format=json` on an already-settled workspace. B and E are the matched release-PGO Cargo binaries at b3360c5eda18 and 34dad66fd2ac. Both used the same embedded version, eight CPUs, released -18 rustc and distributed Wild. Each visit independently restored its source-specific donor, ran one warmup, and measured one ordinary check. Every one of the 128 commands (64 warmups and 64 measured visits) produced the expected 510 typed unit identities, including the same 12 reported dirty, and all 597 literal output paths and complete file hashes. The product manifests cover both historical source states. They have identical path sets and differ in the bytes of four files, one standalone linter metadata file and three native Rust archives. Each command matched its own source state.

| Summary | Observation |
|---|---:|
| Median elapsed time with B, all 32 visits | 4.380 s |
| Median elapsed time with E, all 32 visits | 4.330 s |
| Paired median slowdown, parent source only | +0.566% |
| Paired median slowdown, child source only | −0.607% |

The primary estimate uses each pair’s two elapsed times. The arm medians and source-specific medians are descriptive. The result covers this single host, these two already-settled source states, and the complete change from B to E.

## Kernel and diagnostic controls

Four separate untimed source/arm controls each recorded one full rustc invocation for `ty_python_semantic` and zero Wild invocations. In each source state both Cargo versions read the same 559 short fingerprint filenames. Independent decoding of the kernel ledger tied all of the corresponding open/read events to Cargo’s process and threads.

| Matched files on each source | B | E |
|---|---:|---:|
| Successful opens on the 559 paths | 1,063 | 1,771 |
| Reads returning 16 hexadecimal bytes | 1,039 | 1,747 |
| Exact 16-byte reads and subsequent one-byte EOF probes | 0 | 833 |
| Successful opens under shared registry outputs | 834 | 1,487 |
| Successful opens under workspace outputs | 229 | 284 |

The extra 708 opens included 653 under registry outputs and 55 under workspace outputs. The candidate made 125 fewer successful reads of the previous 32-byte request form. These counts cover opens on the matched short-file cohort, not total Cargo I/O.

Reducing the real visibility of `Token::is_triple_quoted_string` caused both images to return Cargo status 101 twice with the same independently clean E0624 at `ruff_python_index/src/multiline_ranges.rs`, line 50, columns 22–45. Both succeeded after restoring the code.

Run `python3 -IB verify.py` beside the manifest to check the frozen order, 64 clock intervals, per-visit typed and native artifact inventories, short-file events, real error/recovery results, and the preregistered analysis. The separately retained original execution streams are bound by SHA-256. The component represents private package and absolute path identities with digests where appropriate.
