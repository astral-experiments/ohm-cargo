# Fixed protocol and admission rules

The original plan was fixed before candidate performance data. A denotes the exact stripped cfd baseline (`00498cb7…`); B denotes the exact stripped b88 candidate (`77a6a04f…`). Full identities are in [build/identities.json](build/identities.json). All stages use the same owned workload, active Cargo path, physical target/cache, pinned tool inputs, command arguments, and restoration rules.

## Sequence and gates

1. **Discovery:** two pairs, AB then BA. Advance only if both reduce Cargo-parent final Ir and the geometric reduction is at least 5%. These pairs are excluded from every confirmation estimate.
2. **Check sanity:** both variants must converge to a fresh check with no compiler work. One equivalent dirty check pair, AB, is an exploratory regression guard. A candidate Ir regression greater than 0.5% requires investigation. There is no check-speedup or significance claim.
3. **Confirmation 1:** eight fresh pairs, AB, BA, BA, AB, BA, AB, AB, BA.
4. **Native sanity:** eight pairs in the same order as confirmation 1, with no profiler on timed calls. Preparation/restoration are outside the native wall interval. A publication blocker occurs only when geometric candidate wall slowdown is at least 3% **and** the candidate loses at least six of eight pairs. Ties are not losses. This stage permits no positive wall-speedup claim.
5. **Confirmation 2:** eight further fresh pairs, BA, AB, AB, BA, AB, BA, BA, AB.

Each confirmation block independently requires eight positive Ir reductions (two-sided exact sign p = 0.0078125) and a 99% paired-bootstrap lower reduction bound greater than 3%. Use 200,000 paired resamples of log(baseline/candidate), seeds 20261023 and 20261024, and the existing linear-interpolation quantile implementation. Both blocks must pass; discovery is never pooled into them. There is no sample extension, retrospective omission, or source revision after seeing an effect.

## Work and identity checks

Each dirty test-build preflight must contain the same complete compiler argv per artifact: two source compilations and four cached link-only invocations. The preflight is excluded from scored Ir/wall observations. Fixture before/after contents differ with equal lengths; a legitimate before-side command establishes the corresponding state. Each sample preserves source/tool/config identities, namespace and rustc-info state, and the required output identities. Original source and active Cargo bytes are restored and the original test command must converge before the next stage binds live state.

Only Cargo is instrumented (`--trace-children=no`). Final `totals:` is authoritative and must equal the sum of self-cost records, excluding inclusive call records, and the retained stderr `Collected` count. A one-instruction header discrepancy is retained rather than used to select/rerun samples. Known Valgrind allocator fallback warnings remain disclosed. Parent polling/synchronization work is included; compiler/linker and kernel work are excluded.

## Prospective host policy

The instruction-policy amendment was prepared at 06:09:42 UTC and accepted at 06:13:44 UTC on 2026-10-23, before v4 execution began at 06:14:08 UTC. It records all host activity observations without rejecting an otherwise-valid instruction pair for quietness. All twelve discovery observations were retained, including one busy observation. There is no retrospective filtering, subtraction, or sample extension. Scheduling can affect parent instruction counts, and balanced order does not prove pair independence.

The native wall stage retains the original strict `require_quiet()` policy. Its host gate was not weakened by the instruction amendment. Own build/test work remains stopped during measurement. The amendment, original plan, and acceptance hashes are recorded in [protocol.json](protocol.json).

## Exact output exception

Three of the four guarded cached-relink executables retain exact hashes. The fourth is the uvx-test file whose relative suffix is `uv/effec4b1bf4bd279/out/uvx-effec4b1bf4bd279`, size 1,068,558 bytes, mode 0700. Only these complete SHA256 values are allowed:

- `2a95ffd8e63c5972733c276c6b69f93215c25c8125bb214b42d2131ff24b7847`
- `9e16d5f6d25edd2649fe2d799b8536b2a1ba891477877bbeb9badf8dda600a37`

The accepted prior ELF comparison found 33 differing bytes confined to the `.rodata` section-header `entsize` field at offset 1608 and GNU build-ID descriptor at offset 3520. Program headers and all other bytes match. Loaded build-ID metadata differs, so this is not full loaded-image equality. This is an exact file/path/size/mode/two-hash rule, not general ELF normalization; any other hash fails. It was accepted before v4 effects and remains unchanged for later stages. The ordinary library-test executable is not included in these four guards.

## Exclusion and disclosure

Previously discarded attempts remain excluded and opaque; no v3 or M4 totals, timings, stderr, or profiles are included or reused. Only valid terminal cohorts may be added here. The public subset omits raw environments and host process/transport/authentication records while retaining their reviewed admission outcomes and provenance digests. Recomputing the public arithmetic does not replay those private operational checks.
