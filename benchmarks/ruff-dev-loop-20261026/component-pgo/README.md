# Individual Cargo changes with the release PGO data

Each comparison changes one Cargo optimization against the same baseline, Ohm Cargo `461a3d1007ecc997a6d86c7d75e8b518575c8d90`. The frozen Linux binaries were built at the same path with the published Ohm 1.99.0-14 compiler, the release profile, `--features ohm-defaults`, release incremental compilation disabled and the release’s `rustc-pgo.profdata` used for Cargo. The profile SHA-256 is `481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7`. These are matched local PGO builds. Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001`.

The unqualified check reported 520 fresh artifacts in each observation. DynamoRIO counted Cargo’s threads with child following disabled. Each block randomly ordered the six separate two-arm comparisons. Each candidate had six parent-first and six candidate-first pairs across 12 blocks, with seed 802197. For the plain package checks, Callgrind followed children and the only process allowed in a timed profile was Cargo. Artifact rosters were verified before and after the cohort. Seeds were 729532 for borrowed lockfile keys, 527302 for inherited lints, and 642701 for the decoded source cache.

The table includes every treatment and pair. Across the six default-workspace comparisons, the five raw p-values of 0.00216 become 0.01299 after Holm adjustment, and the source-ID p-value remains 0.01515. Its exact two-sided randomization p-values condition on the observed balance of arm order. Median intervals are distribution-free with at least 95% coverage. Use the [standalone Callgrind harness](../registry-manifests/) with `--design paired --pairs 12`. For the default checks, add `--artifact-messages`. For plain package checks, pass `--package` and omit the artifact flag.

A second build of the PGO control after compiling all candidates reproduced every loaded section except the build ID. The 25,303,611-byte `.text` section was byte-identical (SHA-256 `6d434a71f88c1b33b05d51cb43e8c13e83b0e182756510e63d550d2d232ac952`), as were the read-only data, dynamic symbols, relocations and unwind tables. The full executable also contains differing linker symbol and string tables.

## Results

| Cargo change | Ruff workload | Favorable pairs | Median reduction | 95% median interval | Raw randomization p |
| --- | --- | ---: | ---: | ---: | ---: |
| Borrow lockfile identity keys | Default check with Cargo JSON | 11/12 | 0.100% | 0.053–0.126% | 0.00216 |
| Cache the last decoded source string | Default check with Cargo JSON | 12/12 | 0.632% | 0.613–0.652% | 0.00216 |
| Reuse owned registry manifests | Default check with Cargo JSON | 12/12 | 1.190% | 1.149–1.202% | 0.00216 |
| Share inherited workspace lints | Default check with Cargo JSON | 12/12 | 0.657% | 0.636–0.684% | 0.00216 |
| Format only necessary lockfile edge fields | Default check with Cargo JSON | 12/12 | 0.394% | 0.371–0.411% | 0.00216 |
| Reuse the locked source identifier | Default check with Cargo JSON | 10/12 | 0.293% | 0.260–0.315% | 0.01515 |
| Borrow lockfile identity keys | Plain check of ruff_text_size | 12/12 | 0.975% | 0.971–0.982% | 0.00216 |
| Share inherited workspace lints | Plain check of ruff_text_size | 12/12 | 2.440% | 2.429–2.445% | 0.00216 |
| Cache the last decoded source string | Plain check of ruff_python_trivia | 12/12 | 4.455% | 4.453–4.461% | 0.00216 |
