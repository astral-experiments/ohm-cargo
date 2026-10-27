# First observed source inputs in a cold Ruff native test build

This H5 series follows prospective registration 242c2bb8a182f4daa5ecdd8a311c349bb01b01b0 and its distinct traced native qualification 8f2afe815ee1cddad092583f8e522f8599ba8068. Each randomized slot starts with an empty private target and registry build store on the same physical filesystem. Ruff is unmodified at 93526150df. Every command is cargo +ohm test --no-run --locked --offline --message-format=json, with normal trust settings.

All 24 slots and 72 real commands completed their native gates. Each command reported 619 artifacts, including 84 test-profile executables (three use custom harnesses) and 18 ordinary binaries or examples. The runner checked 110 ELF products. Candidate C completed each cold command and both unchanged commands with all 110 exact raw output hashes retained. A/B/D used the previously registered stock linker field exception only after real full links; every other byte must match. Measured jobs were untraced. A separate all-process native preflight checked that the first unchanged control fully compiled ron and launched 50 cached-rustc links and 50 genuine Wild processes. C launched zero of each. The direct ordinary native smoke test and CLI oracles ran outside each triplet's timers.

Cold+first sums the two command endpoints and excludes independent artifact audits performed outside the timer. The table reports each arm’s median command duration and the paired geometric-mean reduction with its 95% block-bootstrap interval. Positive reductions favor C. Small-overhead safety tests use their own one-sided limits in analysis.json.

| Endpoint | Control | Control median (s) | C median (s) | C reduction, % (95% CI) | Holm P |
|---|---|---:|---:|---:|---:|
| cold | D | 264.4112 | 264.3630 | 0.076 (-0.561, 0.703) | — |
| first | D | 5.5213 | 0.7750 | 85.913 (85.490, 86.308) | 0.004329 |
| settled | D | 0.7727 | 0.7765 | 3.128 (-2.914, 8.359) | — |
| cold_plus_first | D | 269.8951 | 265.2038 | 1.833 (1.208, 2.444) | 0.004329 |

Prespecified primary claims passed. Upper-bound cold and settled safety gates passed. All tests and thresholds are listed in plan.json. The stopped first registration used disjoint states and contributes no observations.

Run python3 -B verify.py to rederive the complete comparison from times.csv, including all unchanged byte commitments and the independent native reference for each arm. SHA-256 authenticates the archive files. BLAKE3 authenticates each Cargo OBS1 payload and the 45 filesystem inputs when a complete proof is available. Commands.json.gz retains each command’s timer, Cargo stdout/stderr commitments, per-file whole-native and ELF hashes, source input digests, raw Rust metadata/archive commitments and ordinary CLI oracles. No environment dump or generic syscall read buffer is included.

These timings compare release-profile binaries built on the Ohm 1.99.0-14 lineage. The distributed 1.99.0-16 release separately reproduced the first unchanged full compilation and 50 real links. [Distributed release control](https://github.com/astral-sh/ohm-cargo/tree/2a185bd7acaaee62811b923882a1b71b23c2cad2/benchmarks/ruff-dev-loop-20261027/initial-ron-stock-release-16).

The Cargo implementation in C also starts a compiler capability query on a dirty non-observing library. A separate 24-pair study on the authentic Ruff text-size edit measured an 8.97% build regression (95% interval 4.86% to 12.55%). Its check estimate was 14.19% slower and missed the prespecified Holm threshold. [Dirty non-observer results](https://github.com/astral-sh/ohm-cargo/tree/829c510eae13e5391bd58accab1d4e714c3b7d0b/benchmarks/ruff-dev-loop-20261027/dirty-nonobserver-cost-results).

[Prospective schedule](https://github.com/astral-sh/ohm-cargo/tree/242c2bb8a182f4daa5ecdd8a311c349bb01b01b0/benchmarks/ruff-dev-loop-20261027/initial-ron-first-observer-h5-revision-plan) · [Untimed native qualification](https://github.com/astral-sh/ohm-cargo/tree/8f2afe815ee1cddad092583f8e522f8599ba8068/benchmarks/ruff-dev-loop-20261027/initial-ron-first-observer-h5-revision-native).
