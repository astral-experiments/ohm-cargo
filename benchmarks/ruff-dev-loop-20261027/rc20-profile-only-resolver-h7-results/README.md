# Ruff parser test builds after a profile-only manifest edit

On a 147-unit Ruff test selection, avoiding the extra workspace resolution reduced the median paired duration of the edited command by **33.97%**. The complete edit-plus-first-repeat cycle was **21.91%** shorter. The candidate missed the predeclared 2% noninferiority margin on the unchanged repeat after restoring the manifest.

| Ordinary Cargo endpoint | Parent median | Candidate median | Median paired reduction (95% interval) | Faster pairs | Two-sided exact p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Edited test build | 271.57 ms | 176.07 ms | 33.97% (31.66% to 39.68%) | 26/32 | 0.000535 |
| Immediate unchanged test build | 168.71 ms | 168.69 ms | 2.50% (−2.32% to 4.87%) | 19/32 | 0.3771 |
| Edit plus unchanged repeat | 506.06 ms | 353.86 ms | 21.91% (18.65% to 38.58%) | 27/32 | 0.000113 |

Positive reductions favor the candidate. The marginal duration medians are calculated separately for each arm. The percentage and confidence interval are calculated from paired observations. The apparent edit effect was positive in both directions, 33.65% when reversing the historical change and 34.17% when restoring it.

| Immediate-repeat direction | Median paired reduction | Paired lower bound | Pairs beating −2% | One-sided p | 2% margin |
| --- | ---: | ---: | ---: | ---: | --- |
| After reverse | 3.93% | 0.75% | 13/16 | 0.0106 | Passed |
| After restore | −3.75% | −7.55% | 7/16 | 0.7728 | Failed |

Each direction uses the fifth ordered paired effect for a distribution-free one-sided lower bound with 96.16% coverage. The cumulative decision required success in both directions. All 128 genuine command durations, including a 2.13 s candidate edit and a 1.78 s parent repeat, are retained. The host had four pinned EPYC Milan CPUs. The native preflight checked competing tool processes and CPU utilization before the cohort. There is no continuous per-command systemwide load measurement to attribute the long tails.

## Workload and comparison

The command was `cargo +ohm test --locked --offline --no-run -j4 -p ruff_python_parser --test generate_inline_tests --test fixtures` at Ruff commit `93526150df078af7dd8fc4226cdcc469539d2001`. Each pair reversed or restored the original three root settings from `6dc1031889aa24a0461457409d39861e279242a9`. The edited `[profile.fast-test]` was inactive. The 553-package lockfile stayed byte-identical.

The parent Cargo executable came from `2fe90823d8ea`. Candidate `97e5acfb7b8e` used the same Cargo version stamp and PGO inputs. Its Git parent `9d675d9393b5` differed from the compiled reference only in existing test code. All 239 nonproduct compiler operands and 335 native link inputs of the release builds matched. The measured workspace used the same stock Linux -18 rustc, driver and Wild in both arms.

Before and after the clocks, real native exec controls observed the rustup proxy and Cargo only, with all 147 units fresh. All 265 declared output files matched the separately cold-built reference in full bytes. The 558 plus 1 test inventories, two direct test invocations and the independent parser consumer agreed. The consumer rejected a parenthesized star import. The same concrete proc-macro library was physically opened in both arms, and its three-way invalid attribute combination produced the same error before and after.

Off-clock hardware breakpoints on the actual release Cargo ELF distinguish the full workspace solver from selected-graph resolution. Each edited parent made one full resolver call. Within that call and the later selected resolve, it invoked the lower solver, lockfile TOML parser and graph conversion twice each. Each edited candidate made zero full resolver calls and invoked the selected solver, parser and graph conversion once each. Both arms made the latter three calls once on unchanged repeats.

## Earlier controls

The first native enrollment compared the old warm graph to a genuinely empty build and stopped before scoring. The two histories matched 245 of 265 files. All 474 native codegen-unit payloads examined were byte-identical, while metadata and one proc-macro library differed. The old compiled macro selected an `ignore`/`size_fn` diagnostic on a triple conflict. The independently clean version selected `size`/`size_fn`. The timing studies enrolled both arms from complete separate copies of that one clean generation, verified all 265 exact bytes and required the latter diagnostic throughout. The blocking cohort reused the two physically independent warm ext4 states from the terminal earlier cohort after archiving and verifying each full state.

The first completed 32-pair cohort used Python's timeout polling. Its 50 ms wake interval obscured differences on the repeat. It remains in `initial-quantized/`; none of its clocks enter the table. The separately registered replacement uses blocking child exit with a SIGALRM watchdog outside the timed interval. The first calibration exceeded its 6 ms maximum once. A second preregistered calibration used a prefaulted shared-memory timestamp immediately before child exit. It passed the same bounds across ten durations separated by 6 ms, with 0.61 ms p95 and 0.72 ms maximum exit-to-return delay. The first and second calibration records are in `timer-calibration/`.

## Replaying

Run `python3 -IB verify.py` to check the file manifest and recompute all pair orderings, clock differences, intervals, tests and admission outcomes. The final `blocking/result.json` contains every sorted duration by arm, direction and phase, and `blocking/rows.json` preserves the original order and start/end timestamps. Cargo diagnostic lines replace only the machine-specific target prefix; the original raw stderr and the literal-command digests are retained per command. The cold comparison contains each divergent product digest. The resolver-address observer, change, timer and a bounded new-workspace reproduction are in `reproduce/`.
