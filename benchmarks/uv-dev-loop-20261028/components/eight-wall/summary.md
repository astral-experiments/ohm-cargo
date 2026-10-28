# Native edited test-build time with all eight changes

The whole-command clock covers full-workspace `cargo test --no-run --locked --offline -j8`, including the released Ohm rustc and default native Wild. Each pair builds the same new private-body literal from matched targets. No tests execute.

| Cohort | Baseline median | Candidate median | Median paired reduction [97.73% rank interval] | Improved | Ties | Exact sign p | Gate |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| initial | 6.719 s | 7.232 s | -8.498% [-19.730%, 4.535%] | 9/24 | 0 | 0.307456 | inconclusive |
| replica | 7.389 s | 7.583 s | 1.654% [-13.504%, 10.399%] | 14/24 | 0 | 0.541256 | inconclusive |

**No repeatable whole-command speedup established.**

Before and after timing, native traces verified six released rustc processes and five real Wild invocations per arm. Every one of the 96 timed commands rebuilt only uv and reported the complete 72-executable test roster. The two Cargo binaries were independently self-trained. The baseline linker is the matched release-source Wild, and the candidate linker contains both Wild changes.
