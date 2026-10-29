# Ordinary Ruff archive mechanism screen on replacement Milan

The Milan stage1 archive screen **failed** its registered mechanism gate. All eight pairs completed, with 32 ordinary Cargo commands. 6/8 pairs had a positive conservative archive saving. The median lower-bound saving was 0.31% of the ordinary A edit-plus-repeat, and the median whole-loop B/A ratio was 0.9955. The gate required six positive bounds, a median of at least 1%, and a whole-loop ratio of at most 1.02.

| Pair | Source | Order | A edit + repeat, s | B edit + repeat, s | A lower minus B upper archive time, ms |
|---:|---|---|---:|---:|---:|
| 1 | P edit | BA | 14.872 | 15.013 | 61.3 |
| 2 | H restore | AB | 14.774 | 14.720 | 105.5 |
| 3 | P edit | AB | 16.687 | 15.172 | 37.6 |
| 4 | H restore | AB | 14.909 | 14.805 | -167.9 |
| 5 | P edit | BA | 14.692 | 14.974 | -219.1 |
| 6 | H restore | BA | 16.644 | 15.906 | 69.4 |
| 7 | P edit | AB | 14.758 | 15.243 | 29.6 |
| 8 | H restore | BA | 14.874 | 14.793 | 57.6 |

Both arms ran the ordinary Ruff package build and its immediate unchanged repeat at the canonical source and SDK paths. The passive observer ran on CPU 8, and the ordinary processes used CPUs 0–7. Complete archive hashing, literal bytes comparison and native caller checks ran after both command clocks. [Registered design](https://github.com/astral-sh/ohm-cargo/tree/86fd410922315ae22b9d3de58f50b30ba1e8939a/benchmarks/ruff-dev-loop-20261027/rc19-rlib-observed-name-screen-plan) · [Milan native evidence](https://github.com/astral-sh/ohm-cargo/tree/262963ad54125a4597aacee71ca500e159f594fd/benchmarks/ruff-dev-loop-20261027)

Run the SHA256SUMS check, then run selftest.py and verify.py with Python 3. The reader replays the exact randomization, reconstructs each command wall time and archive creation/publication bounds from its raw passive event record, counts the 10/0 Cargo compile lines, and checks the 452-path roster and authenticated 101,719,820-byte archive and program digests. The export preserves original stdout and stderr digests, and replaces private path prefixes in the diagnostic text. These measurements use the stage1 compiler. A production optimization would require its own independently qualified whole-command trial on both hosts.
