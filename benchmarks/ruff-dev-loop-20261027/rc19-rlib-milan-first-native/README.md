# Milan first edit with the in-process rlib writer

The first Milan comparison failed the required raw-archive equality check. Both Cargo arms began with the same complete original archive. Each built ten libraries on the historical parent edit and ran zero compilers on its immediate repeat. All ten resulting rlibs differed between arms, including the nine upstream libraries that never received the prior-archive option. The release-trial admission stopped at this pair with zero clocks. The initial condition does not isolate a bug in the writer.

| Observation | Ordinary writer A | Prior supplied by Cargo B |
| --- | --- | --- |
| Source Cargo | `235f9228651b` | `0299c77b2ca9` |
| Fresh original build | 248/248, no compiler | 248/248, no compiler |
| Parent edit / repeat | 10 full rustc / 0 | 10 full rustc / 0 |
| Capability queries on edit | 0 | 1 |
| First edited root SHA-256 | `23a695c9e8c82a6b2c60e3d91d9e7a43a2e2197225b0f67e132e4e8b2f31178f` | `f65dca9af2207a0d3693486a5f55480e77be4816e9533814d805dca851e20c61` |
| Independently linked SIM222 caller | lines 2, 3, 4 | lines 2, 3, 4 |

The 248 typed artifacts and all 452 declared output paths matched. The ten real compiler invocations matched once the selected linter's single `-Zohm-rlib-origin` argument was removed. Neither arm ran rustc link-only, GCC, collect2 or Wild during the package edit or repeat. The separate SIM222 callers did perform real native linking. Their resulting executables were byte-identical across A/B. Their separately empty edit reference also printed lines 2, 3 and 4, from its own different root archive (`de71d17c…`) and executable. The original empty build and both held old file descriptors bound `3dc42530…`; its caller printed only line 1. Each clean build reported 0/248 fresh followed by 248/248 fresh.

The two 101,719,820-byte first-edit archives contain 260 members in the same order, with identical offsets, sizes and literal member headers. Their GNU symbol index, `lib.rmeta` and each of the 256 code-generation unit object payloads are byte-identical. The `//` string table changes all 256 final name components from `.0ub3itk.rcgu.o` to `.07y2oqw.rcgu.o`. The `lib.rmeta-link` member contains the same changed strings in its `.rmeta-link` section, with exactly 1,536 different bytes in 256 six-byte ranges. These link-visible names were included in the registered whole-output comparison. The worktrees received independently materialized bytes of the same three Git files with current mtimes, as planned. No source of the name variation was inferred from this single pair.

The first independent edited cold command, repeat and caller passed. Its additional custody guard then rejected a Btrfs parent subvolume’s changed transaction generation. A separate blank filesystem reproduced the exact mechanism: making a writable child advanced the read-only parent from generation 7 to 8, with the complete file tree and its other identity fields unchanged. A kernel-enforced read-only inspection authenticated all 968 pristine registry files and the 13,051-inode trained donor. The authorized continuation reused the successful cold result and verified the full donor before and after the first pair. The original failure, custody authorization and final raw product failure are retained separately.

`evidence.json.gz` contains source and tool digests, both first-edit member inventories, every physically observed process digest and return code, all declared output file digests, the three-file input binding and cold/caller receipts. `member-detail.json` preserves the root member byte ranges and source mtimes. The larger original artifacts remain in the private Milan study. Run `python3 -IB verify.py` to reproduce the comparison offline.
