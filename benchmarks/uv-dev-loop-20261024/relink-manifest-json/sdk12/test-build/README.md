# Cached relink-manifest parsing during uv test builds

Each sample ran the first dirty `cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8` after the equal-length uv library comment edit. Callgrind counted instructions in the Cargo parent. The two native uv compiler calls and four cached relinks used the fixed SDK12 rustc and Wild.

| Machine | Paired Cargo instruction reduction | 99% interval | Pairs improved | Exact two-sided sign p |
| --- | ---: | ---: | ---: | ---: |
| 1 | 10.185% | 10.079% to 10.343% | 8/8 | 0.0078125 |
| 2 | 10.045% | 9.867% to 10.124% | 8/8 | 0.0078125 |

The two machines used identical source-built Cargo binaries and independent warm states. Each block used eight baseline/candidate pairs in balanced order. The order reversed on the second machine. The fixed success rule required eight wins and a 99% lower reduction bound greater than 1% on each machine.

The raw-output validator expected two legacy names for native stdout and stderr. We identified this during collection while both effects were masked. A reviewed adapter resolved those names from the original, already authenticated preflight captures. Each machine retained the original missing-field failure and then ran the original validator with exactly those two references per arm. An added wrapper check stopped after both machines had written their raw-gate reports. Python marshal can serialize the same code object differently when a literal is referenced. We reproduced this on a synthetic function, checked code-object identity and opcode bytes directly, and reran offline validation. Both raw-gate reports reproduced byte for byte before any effect was opened. All sampling, output and statistical predicates used their frozen bytes. [Validation receipts](validation.json).

Run `python3 -I -B reproduce.py` to verify the 32 complete public profiles and compute both estimates. See [fresh-build instructions](REPRODUCE.md) for the matched Cargo build, expanded Callgrind controls and uv fixture.
