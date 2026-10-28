# First observed source inputs in a cold Ruff native test build

This H4 series follows prospective registration b958edb54d0bc8528b690a6867f2113b790292e9 and its distinct traced native qualification ea664b70b19cfb94111aefcbdd590edebaa32da0. Each randomized slot starts with an empty private target and registry build store on the same physical filesystem. Ruff is unmodified at 93526150df. Every command is cargo +ohm test --no-run --locked --offline --message-format=json, with normal trust settings.

All 54 slots and 162 real commands completed their native gates. Each command reported 619 artifacts, including 84 test-profile executables (three use custom harnesses) and 18 ordinary binaries or examples. The runner checked 110 ELF products. Candidate C completed each cold command and both unchanged commands with all 110 exact raw output hashes retained. The A and B controls permitted only the registered stock linker width and derived build-ID fields after real full links. Every other byte had to match. Measured jobs were untraced. A separate all-process native preflight checked that the first unchanged control fully compiled ron and launched 50 cached-rustc links and 50 genuine Wild processes. C launched zero of each. The direct ordinary native smoke test and CLI oracles ran outside each triplet's timers.

Cold+first sums the two command endpoints and excludes independent artifact audits performed outside the timer. The table reports each arm’s median command duration and the paired geometric-mean reduction with its 95% block-bootstrap interval. Positive reductions favor C. Small-overhead safety tests use their own one-sided limits in analysis.json.

| Endpoint | Control | Control median (s) | C median (s) | C reduction, % (95% CI) | Holm P |
|---|---|---:|---:|---:|---:|
| cold | A | 274.6826 | 275.0533 | -0.265 (-0.923, 0.403) | — |
| cold | B | 275.3001 | 275.0533 | 0.101 (-0.640, 0.823) | — |
| first | A | 5.7373 | 0.8142 | 84.964 (83.399, 86.156) | 0.001 |
| first | B | 5.7645 | 0.8142 | 85.107 (83.462, 86.287) | 0.001 |
| settled | A | 0.8183 | 0.8342 | -1.509 (-10.127, 5.971) | — |
| settled | B | 0.8320 | 0.8342 | 1.691 (-5.955, 9.157) | — |
| cold_plus_first | A | 280.0733 | 275.9551 | 1.483 (0.845, 2.148) | 0.001 |
| cold_plus_first | B | 281.3216 | 275.9551 | 1.853 (1.106, 2.580) | 0.001 |

All four primary comparisons passed at Holm-adjusted P = .001. Both cold safety bounds also passed. The one-sided 98.75% upper bounds were +1.017% against A and +0.755% against B, inside the +3% budget. The settled-repeat bounds failed the +5% overhead budget against both controls. C was bounded at +11.385% and +105.0 ms against A, and +7.127% and +67.4 ms against B. The absolute budget was +100 ms. These intervals did not establish a settled regression. The study did not qualify the product against its registered safety thresholds. The stopped first registration used disjoint states and contributes no observations.

Run python3 -B verify.py to rederive the complete comparison from times.csv, including all unchanged byte commitments and the independent native reference for each arm. The SHA-256 manifest covers the evidence files. Cargo uses BLAKE3 to seal each complete OBS1 record and to verify the 45 corresponding input checksums. Commands.json.gz retains each command’s timer, Cargo stdout/stderr commitments, per-file whole-native and ELF hashes, source input digests, raw Rust metadata/archive commitments and ordinary CLI oracles. No environment dump or generic syscall read buffer is included.

These timings compare release-profile binaries built on the Ohm 1.99.0-14 lineage. The distributed 1.99.0-16 release separately reproduced the first unchanged full compilation and 50 real links. [Distributed release control](https://github.com/astral-sh/ohm-cargo/tree/2a185bd7acaaee62811b923882a1b71b23c2cad2/benchmarks/ruff-dev-loop-20261027/initial-ron-stock-release-16).

The Cargo implementation in C also starts a compiler capability query on a dirty non-observing library. A separate 24-pair study on the authentic Ruff text-size edit measured an 8.97% build regression (95% interval 4.86% to 12.55%). Its check estimate was 14.19% slower and missed the prespecified Holm threshold. [Dirty non-observer results](https://github.com/astral-sh/ohm-cargo/tree/829c510eae13e5391bd58accab1d4e714c3b7d0b/benchmarks/ruff-dev-loop-20261027/dirty-nonobserver-cost-results).

[Prospective schedule](https://github.com/astral-sh/ohm-cargo/tree/b958edb54d0bc8528b690a6867f2113b790292e9/benchmarks/ruff-dev-loop-20261027/initial-ron-first-observer-h4-revision-plan) · [Untimed native qualification](https://github.com/astral-sh/ohm-cargo/tree/ea664b70b19cfb94111aefcbdd590edebaa32da0/benchmarks/ruff-dev-loop-20261027/initial-ron-first-observer-h4-revision-native).
