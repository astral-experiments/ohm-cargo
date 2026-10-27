# Paired cargo build and test --no-run times on three Ruff parser edits

Both releases ran the same complete Ruff workspace commands with normal Ohm defaults on the dedicated H5 host. The experiment interleaved all six edit/command combinations, balanced arm order independently in each direction, and timed exactly 192 ordinary Cargo processes. Every measured command had an immediate, separately traced, fully fresh control. The 48 independent traced pre- and post-study transitions had to match the first-exposure rustc and Wild counts exactly. A compiler, linker, source or roster discrepancy terminates the family.

Each result reports 16 pairs, geometric time saved, a 95% interval resampling whole edit/restoration blocks, and a two-sided exact randomization p-value. The six p-values are adjusted together with Holm. Elapsed time includes Cargo and its children. Setup, source switching, diagnostics checks, tracing and the unchanged follow-up command are outside the timer. Every timed invocation and ordinary stderr/stdout is retained.

The CPU admission check deferred the first start before any timed process or observation existed. Two separate four-second checks found the assigned CPUs quiet. The same registered runner and prepared build directories then started the sequence at its first pair. The admission history records the original file digests.

Run `python3 -B verify-wall.py` here with zstd installed. The verifier streams the raw Cargo outputs, confirms the dirty/fresh and product rosters and compares the native invocations with the corresponding descriptive measurements. The result analyzer can also run separately.

| Edit | Cargo command | #232 median | #233 median | Paired reduction (95% interval) | Faster pairs | Holm p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Pending indentation | `build` | 18.36 s | 18.92 s | 0.9% (-5.1–8.8%) | 7/16 | 1.00000 |
| Signed-pattern diagnostic | `build` | 18.70 s | 5.54 s | 70.2% (68.8–71.3%) | 16/16 | 0.00245 |
| Single-string allocation | `build` | 18.72 s | 5.49 s | 70.0% (68.9–70.9%) | 16/16 | 0.00245 |
| Pending indentation | `test --no-run` | 24.95 s | 25.46 s | -1.4% (-5.1–2.5%) | 7/16 | 1.00000 |
| Signed-pattern diagnostic | `test --no-run` | 24.75 s | 7.86 s | 69.0% (68.3–69.7%) | 16/16 | 0.00245 |
| Single-string allocation | `test --no-run` | 24.48 s | 7.95 s | 68.5% (67.3–69.6%) | 16/16 | 0.00245 |

The public archive replaces one machine-specific Cargo registry checkout basename with a stable alias. The translation preserves all other Cargo output, all times, every native job and all original witness records. The raw archive passed the original verifier before this export. Each translated member has its original and public digest and substitution count in `portable-receipt.json`. The offline verifier recomputes the normalized unit rosters and checks each original timing witness. `verify-original-wall.py` verifies the unmodified archive on its originating system.
