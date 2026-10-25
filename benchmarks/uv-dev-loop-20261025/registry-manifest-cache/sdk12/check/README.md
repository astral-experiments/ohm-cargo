Private registry-manifest cache: warm dirty check

This private packet contains all 32 accepted Cargo-parent Callgrind profiles from two independent fixed eight-pair blocks. Run `python3 -I -S -B reproduce.py` here to authenticate every profile, reproduce final/self/stderr instruction joins and replay both 99% paired bootstrap estimates, order strata and exact sign tests.

The two hosts reduced Cargo-parent instructions by 5.2655% and 5.3943%. Each had eight wins, exact two-sided p = 0.0078125, and a lower 99% reduction bound above the prespecified 1% threshold. Results are separate and unpooled. Compiler, linker and build-script children were native and outside these counters; this is not a whole-build instruction or elapsed-time claim.

The baseline is published Cargo #235, which already contains #234. The candidate adds the exact three-file registry-manifest JSON cache patch. Both production binaries embed fd7a25d7 and were built with the same stock Rust 1.99 ThinLTO recipe; the SDK12 compiler used for uv is a separate fixed workload tool. The candidate binary is 1,122,888 bytes larger. This baseline does not contain the separate five-change Cargo combination.

The observed warm cache held 445 committed slots and 803,161 logical bytes per host. These are retained contents, not total writes or a measured production hit count. The bounded 4,096-slot cache permits at most 64 KiB per committed entry. Cache misses can incur extra parsing, encoding and writes. The separately gated cold supplement must report either sign and per-host instruction amortization before a publication decision; no cold profiles or inferred break-even are present here.

All four excluded native/profile preflights, parser/codec scout observations, and cold/native observations are outside these estimates. Both complete raw/restoration gates preceded all 32 metric joins and either host estimate. Each arm retained its own exact rmeta output identity; no cross-arm metadata byte-identity claim is made. The private validator also checked original source/lock restoration, usable child contexts, diagnostics, fresh commands and parked banks. See `validation.json`, `endpoint-inputs.json` and `correctness.json`.

Raw function/call/cost records remain intact. Only command executable spelling and source/object path labels were substituted; original raw/gzip/stderr hashes and the unchanged nonpath stream hash are in `profiles/PROFILE-MANIFEST.json`. `REPRODUCE.md` records the source, build, profiler and fixture recipe.

No public write is authorized by this packet. The independent native A/A noise gate and whole-command comparison remain required; a replicated native elapsed regression withholds a PR.
