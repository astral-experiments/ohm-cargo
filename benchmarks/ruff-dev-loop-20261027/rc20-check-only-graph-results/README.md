# Cargo check planning on a real Ruff dependency edit

The candidate missed the preregistered standalone PR gate on this host. Each of 80 pairs used the registered release-profile Cargo control and treatment on the same released -19 compiler. Every arm started with an independently restored check-only state. The actual command was `cargo +ohm check --locked --offline -p ruff_python_trivia --message-format=json`. The 480 timed ordinary Cargo subprocesses, all typed artifact rosters and all 18 subsequent native anchors passed before analysis. [Prospective protocol](https://github.com/astral-sh/ohm-cargo/tree/0f2276b6ee86256801ccaf063eac239a5d00f67e/benchmarks/ruff-dev-loop-20261027/rc20-check-only-graph-plan).

| Edit direction | Endpoint | Pairs | A median ms | B median ms | Paired saving % [95% CI] | Paired saving ms | B faster | Holm p |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| chronological | settled | 32 | 107.17 | 104.40 | 1.69% [-1.79, 5.44] | 1.79 | 20/32 | — |
| chronological | edited | 32 | 737.83 | 737.60 | -0.75% [-2.99, 2.10] | -5.40 | 14/32 | 0.62836 |
| chronological | repeat | 32 | 64.31 | 63.49 | 1.33% [-1.50, 3.27] | 0.85 | 19/32 | — |
| chronological | combined | 32 | 801.60 | 800.67 | -0.74% [-2.31, 1.86] | -5.90 | 14/32 | — |
| reverse | settled | 32 | 109.85 | 107.84 | 0.32% [-4.47, 4.02] | 0.34 | 17/32 | — |
| reverse | edited | 32 | 355.73 | 346.07 | 2.83% [1.46, 3.69] | 9.71 | 22/32 | 0.62836 |
| reverse | repeat | 32 | 62.40 | 61.74 | 2.06% [-6.85, 3.34] | 1.26 | 19/32 | — |
| reverse | combined | 32 | 417.94 | 407.18 | 2.17% [1.05, 3.42] | 9.15 | 22/32 | — |
| source-only | settled | 16 | 112.62 | 110.62 | 4.09% [-3.65, 7.54] | 4.55 | 10/16 | — |
| source-only | edited | 16 | 228.07 | 222.81 | 1.05% [-3.06, 3.71] | 2.33 | 9/16 | — |
| source-only | repeat | 16 | 66.61 | 64.57 | 1.67% [-3.69, 4.88] | 1.07 | 10/16 | — |
| source-only | combined | 16 | 295.07 | 286.48 | 1.43% [-2.03, 3.05] | 4.02 | 10/16 | — |

The co-primary endpoints are the chronological and reverse edited checks. The combined endpoint adds that edit to its immediately following unchanged check. The settled endpoint is the unchanged check before the edit. Intervals resample complete registered blocks. The two-sided block sign-flip tests share a single Holm adjustment for the two primary directions. The source-only control changes the real Ruff implementation while keeping its newer manifest and lockfile.

- The chronological direction missed its full gate. Settled noninferiority passed and immediate-repeat noninferiority passed.
- The reverse direction missed its full gate. Settled noninferiority missed and immediate-repeat noninferiority missed.
- The distinct source-only edited guard missed its 3% and 5 ms noninferiority bounds.

This study measured a package-scoped `cargo check` on one Linux host. The full historical patch required four compiler jobs going forward and one going backward on both arms. The treatment removed the second ordinary dependency resolution. No linkers ran in these tested checks. The previous genuine Ruff caller, invalid E0432 and E0308 checks, no-marker and marker controls, and the earlier rejected acquisition attempts are in the separately published native and registration packet.

Run `python3 -IB verify.py`. The verifier reconstructs each duration from its raw monotonic timestamps, checks complete ordering and output hashes, joins the six native pre/post sequences, and repeats the prospective statistics. The compressed public ledger carries SHA-256 commitments to the original Cargo JSON, diagnostics and native traces. Those original streams remain unchanged in the private source collection.
