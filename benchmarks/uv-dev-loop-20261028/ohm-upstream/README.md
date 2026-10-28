# Ohm duplicate check

Checked through **2026-10-28 21:00 UTC**. None of the eight drafts duplicates an independent Ohm change found in released sources, integration branches or the related pull requests. Ohm 1.99.0-18 was published while the -17 performance study was running. Its Cargo pin is `7caf39914`, its Rust pin is `a4fa11bcd`, and it retains the same Wild 0.11.0 archive as -17. All five Cargo patches apply in sequence to -18. [Release manifest](https://github.com/astral-sh/ohm/blob/ohm-1.99.0-18/toolchains/1.99.0/18.json)

| Draft | Work still present in Ohm -18 |
| --- | --- |
| [ohm-cargo #264](https://github.com/astral-sh/ohm-cargo/pull/264) | Three build and fingerprint traversals still copy the `UnitDep` values they read. |
| [ohm-cargo #267](https://github.com/astral-sh/ohm-cargo/pull/267) | Cargo still formats dependency-table paths before discovering whether any unused keys need a warning. #250 caches unused-key data separately. |
| [ohm-cargo #268](https://github.com/astral-sh/ohm-cargo/pull/268) | Feature resolution still performs the filtered dependency traversal at three sites without the proposed cache. |
| [ohm-cargo #269](https://github.com/astral-sh/ohm-cargo/pull/269) | The public depfile renderer still creates owned strings for unescaped paths and formats each dependency into the output buffer. |
| [ohm-cargo #270](https://github.com/astral-sh/ohm-cargo/pull/270) | The locked and precise version transitions still clone the current `VersionReq`. |
| [ohm-rust #247](https://github.com/astral-sh/ohm-rust/pull/247) | All 55 releases retain the same scalar `compare_components` loop. Both patched files are byte-identical between -17 and -18. |
| [ohm-wild #45](https://github.com/astral-sh/ohm-wild/pull/45) | The bundled linker resolves and formats undefined-symbol diagnostics along the existing path. |
| [ohm-wild #46](https://github.com/astral-sh/ohm-wild/pull/46) | The bundled linker still uses the general ELF rules for the default `.text*` and `.rela*` cases. |

The Cargo source census covered 55 published manifests, 282 named branches and 141 open PR heads. Each implementation occurs on its own draft and descendants in this stack. Of 227 previously posted Cargo PRs, 147 touched one of the seven affected files under either source layout and received a separate hunk-level check. [Cargo source evidence](cargo-history/README.md)

The Rust audit covered 51 distinct released Rust pins, 312 named branches and 139 open PRs. The Wild audit checked all 44 Ohm Wild PRs. The sole merged Wild PR changed the README and CI workflow. [Rust source evidence](rust/README.md) · [Wild source evidence](wild/README.md)

## Cargo #269 on Ohm 1.99.0-18

Three earlier changes reached the release. #175 skips depfile work when no public output needs one. #176 shares parsed inputs and avoids rewriting an identical file. #262 reduces collection to paths. #269 changes how the surviving paths are rendered. Its immediate predecessor and candidate were rebuilt on the exact -18 Cargo source with matching release-style, non-PGO flags and the distributed -18 compiler. Each arm opened the real public `uv.d` during a warm `cargo build` and regenerated identical depfiles in a separate correctness check. [#175](https://github.com/astral-sh/ohm-cargo/pull/175) · [#176](https://github.com/astral-sh/ohm-cargo/pull/176) · [#262](https://github.com/astral-sh/ohm-cargo/pull/262)

| Counter | Pairs improved | Median Cargo instruction reduction | Median interval | Two-sided sign p | Balanced-order p |
| --- | ---: | ---: | ---: | ---: | ---: |
| DynamoRIO | 12/12 | 1.623% | 1.604% to 1.636% | 0.000488281 | 0.0021645 |
| Cachegrind | 8/8 | 1.968% | 1.958% to 1.982% | 0.0078125 | 0.0285714 |

The -18 comparison **passed both registered cohorts**. Its endpoint is Cargo instructions on a warm, full-workspace `cargo build`. The original edited test-build and elapsed-time results in the eight-draft study were measured on -17. [Registered -18 conditions](cargo/depfile-plan.json) · [Raw -18 primary](cargo/count-initial/pairs.csv) · [Raw -18 repeat](cargo/count-replica/pairs.csv) · [Full -17 evidence](https://github.com/astral-sh/ohm-cargo/tree/360685aa51f204690585a3d196767bd788b34f42/benchmarks/uv-dev-loop-20261028)

The supplemental archive contains a self-contained release-18 replay packet and a standard-library Python verifier. After extracting the outer archive, run `python3 -I -S verify-receipts.py` to recompute both statistical results and replay the source classification. [Release-18 reproduction guide](cargo/reproduce.md) · [Release-18 replay packet](cargo-release18-audit.zip)

## Drafts and feedback

All eight drafts were open at the last check, with 0 submitted PR reviews and 0 conversation comments. The five Cargo drafts had eight passing jobs and one skip each. Rust had three passing jobs. Both Wild drafts had 24 inherited setup failures before checkout and three passing dedicated jobs each. [Wild #45 validation](https://github.com/astral-sh/ohm-wild/actions/runs/40732795058) · [Wild #46 validation](https://github.com/astral-sh/ohm-wild/actions/runs/40745398550)
