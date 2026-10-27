# Cost on a Ruff edit with no foreign source observation

All 96 preregistered timed commands and the 40 independent unscored process controls passed their output and ordinary Rust API checks. Incremental check and build used a complete reverse of Ruff commit 61a49c89 and its restoration. They selected one real library, ruff_text_size, from the unchanged workspace. The two Cargo arms held the PGO+BOLT compiler constant. No foreign-span marker was present. Unscored traces counted one extra rustc capability process on each true candidate compile and zero on an unchanged repeat. Actual operation was the same for both tools, including rebuilding the library, rejecting the removed method with E0599 and printing 2-6 after restoring it.

Protocol commit 0cdc35f5bde38a945e7dd067e23969a9aefec8ad froze 24 balanced paired historical edits per command, source and output gates, and actual direction-stratified randomization tests. The rows below report geometric-mean paired overhead, 95% bootstrap intervals and arithmetic mean absolute overhead. The numerical small-cost bound requires both an upper one-sided 97.5% overhead below 3% and an absolute upper bound below 5 ms in each endpoint.

| Command | Prior median (ms) | Candidate median (ms) | Mean paired overhead (ms) | Geomean overhead, % (95% CI) | Holm P | Small-cost bound |
|---|---:|---:|---:|---:|---:|---|
| check | 182.388 | 199.447 | +31.325 | +14.187 (+0.745, +29.035) | 0.0757951 | fail |
| build | 194.955 | 211.752 | +16.979 | +8.969 (+4.858, +12.548) | 0.000787092 | fail |

The check output’s complete rmeta and the build output’s complete rmeta plus both native codegen objects matched each same-source independent full reference throughout. Raw rlib contents differ naturally even under separate baseline builds because rustc randomizes the two auxiliary object member names. Each row preserves the full raw archive hash and whole per-member hashes. The only permitted Rust link-receipt substitutions are the two names actually enumerated in the corresponding archive. The final unchanged B and C check/build outputs matched their own previous raw values.

Run python3 -B verify.py to check the raw timing rows and native controls and independently recompute analysis.json. The associated complete source/ordinary caller, registration, deployment parameters and self-tests are in the prospectively published dirty-nonobserver-cost-predeclared directory. This one-package separate endpoint measures the cost of discovery, while the 619-unit ron first-repeat experiment measures its benefit.
