# Cached Rust objects for cfg-disabled native Ruff API tests

This Cargo-only prototype replaced one or two full rustcs with real link-only rustcs on genuine workspace edits. Each command still used native GCC, collect2 and Wild. The whole-command screen missed its prospectively chosen advance threshold on both endpoints.

| Edit | Stock median | Candidate median | Geometric mean time saved | Median paired time saved | Candidate faster | Two-sided blocked P |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ty_wasm implementation | 2.9354 s | 2.8489 s | 0.465% | 3.550% | 4/8 | 0.9444 |
| Python parser diagnostic | 7.8657 s | 7.7735 s | 1.119% | 0.172% | 4/8 | 0.5000 |

The registered threshold for a separate confirmation study was at least six faster pairs out of eight and at least 1% geometric improvement on one edited endpoint. The other endpoint also had to stay within a 2% slowdown. No candidate met the first condition.

| Immediate no-op after edit | Stock median | Candidate median | Geometric mean time saved | Candidate faster | Two-sided blocked P |
| --- | ---: | ---: | ---: | ---: | ---: |
| ty_wasm implementation | 0.8945 s | 1.1407 s | −8.383% | 3/8 | 0.5556 |
| Python parser diagnostic | 1.0825 s | 0.8864 s | 15.392% | 4/8 | 0.1111 |

The full command was cargo +ohm test --no-run --locked --offline --message-format=json on Ruff 93526150df078af7dd8fc4226cdcc469539d2001. The actual default workspace delivered 619 Cargo artifacts, 102 runnable outputs and 110 ELF products throughout. We timed whole Cargo invocations with a monotonic wall clock. The outer runner prepared sources, verified the raw binary identity, inspected behavior and counted processes in separate invocations. Each arm had an independent writable target and build directory mounted at identical canonical paths on a dedicated ext4 disk. The eight pairs per endpoint were balanced over direction and arm order. The screen allocated CPUs 0–23 on one AMD host and gave Cargo eight jobs. The official registration fixes the historical edits, statistic, orders and control requirements. [Prospective registration](https://github.com/astral-sh/ohm-cargo/tree/e7e1be37cde68e35e6c1adb8c3d78726917d2916/benchmarks/ruff-dev-loop-20261027/cfg-disabled-real-link-screen-plan)

The trained wasm-only edit used one full plus one link-only rustc, versus two full rustcs with stock, and both arms launched two real Wild linkers. The parser edit used four full plus 64 link-only rustcs, versus six full plus 62 link-only with stock, and both launched 67 real Wild linkers. The ordinary integration tests themselves remained byte-identical on both arms and listed zero tests on Linux. An independent Rust caller proved the real wasm API addition and removal, and the Ruff CLI exhibited the expected parser diagnostic in both revisions. The initial genuine dirty compilation on a copied stock baseline trained the two test units and took the stock compiler path. The companion qualification packet provides its specific costs and the active-CFG and failing-link cases.

## Verifying the outcomes

Run python3 -B verify.py. This checks both original CSVs against their individual invocations, the prospectively assigned order, before/after process rosters, Cargo diagnostics, Rust callers, the CLI checks, and all 110 raw ELF identities of every edited command. It independently recomputes both tables from the CSV files. The arithmetic for each endpoint uses 36 admissible source-direction-balanced sign assignments. The screen is exploratory.

The runner retained every existing measurement when a raw ELF variant of the untouched visitor test appeared on the initial untimed parser preflight. The wasm endpoint had already finished and no parser timing had begun. The extra stock oracle recompiled that same source and independent target under two GNU-make jobserver token budgets, issuing one full stock rustc and one real bundled Wild on each command. The two complete visitor files had SHA-256 be3ca1d329719b481a103233d84ca23909857028c8cb79a64cfe7a17ed2ed007 and cc4e1378a26a18ad20c69cccbdf0d5790b2320f68c6cadb32589cdd83d5ca574. Their contents outside the registered .rodata entry-size header and GNU build-ID fields gave SHA-256 7fc141a6115e8228dcab61e3eaf9c207d46d458511e39610e242b48bc002b5cc. The same stock-full/byte-exact gate later verified the edited visitor and the restored simple_tokenizer and ruff_python_semantic variants. All observations kept their original timestamps, source states, order and outcomes. The exact fixed measurement program has SHA-256 69055ed7558ef06c5fdb6892703e71b92422ccc32144797bbe2214f7722a2928. The continuation reused it and only admitted individually reproduced raw stock bytes.

The runner directory holds the executed benchmark-specific scripts. Running them again requires the pinned source/subjects, equivalent private stores and the paths and host checks in shared.py. The portable verifier uses only the exported observations and the Python standard library. The candidate.patch file describes the exact change on Cargo d38fdd02503662de04c52f5f370f5dd81bddf868. It is included for reproducibility of this rejected screen. No measurement ran Ruff test bodies.
