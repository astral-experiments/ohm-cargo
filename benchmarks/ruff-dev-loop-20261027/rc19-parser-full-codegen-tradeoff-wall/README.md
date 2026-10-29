# Ruff parser full-codegen fallback cost

On this four-core coordinator, the median ordinary edit command took 2.5413 seconds with cached codegen and 2.5920 seconds with full rustc. The median paired cost of disabling cached relinking was 1.53% (95% paired bootstrap interval 0.92% to 2.79%). Full compilation took longer in 12/12 pairs. The two-sided balanced randomization test gave p=0.021645. Median paired absolute difference was 0.0390 seconds.

Each paired command began with the same genuine historical parser edit after restoring its arm's original test build. Two separately warmed stores mounted at identical paths used source-stamped release-PGO Cargo 2447f7f4, private stage1 Rust 5e3de497 and stock Wild. Both commands targeted Ruff’s generator and fixtures. The fallback command added only the Cargo option `-Zrelink-only=no`. The 14 unscored native commands independently verify the two additional full compilers, both real links and exact output parity. Each timed slot ran ordinary Cargo with no tracer or extra output flags. Sender-side hashes commit to both streams, native executable identity, test inventories and actual test bodies. All 48 post-check commands found all 147 targets fresh, covering the scored edits and the interspersed unscored restorations.

This single-host estimate covers the cost of disabling that entire command option, including sidecar emission and preserving temporary objects. The narrower compiler-default change that retains native codegen evidence is a different subject.

Run `python3 -IB analyze.py --directory .` to re-read the 24 clocks, paired assignment and all typed post-checks. `clocks.csv` preserves both timestamp endpoints, and `raw-bindings.json` binds each original output and the earlier native admission.
