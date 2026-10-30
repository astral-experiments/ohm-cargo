# Disk use after switching Ruff branches

This comparison counts the *entire* Cargo target and build directories for `cargo +ohm build -p ruff_python_parser`. It includes intermediates, libraries and incremental sessions for the full dependency graph. It counts allocated filesystem blocks and deduplicates hard links across both roots by device and inode. GNU `du -sx -B1` agreed at all 24 successful visits. The checkout, SDK and registry download directory live outside the two roots. [Per-visit observations](observations.json)

| Native Cargo visit | Parent | With branch retention | Relative size |
| --- | ---: | ---: | ---: |
| First build of the parent branch | 257 MiB | 257 MiB | 1.00× |
| First build of the feature branch | 273 MiB | 378 MiB | 1.39× |
| Return to the parent branch | 288 MiB | 380 MiB | 1.32× |
| Return to the feature branch | 258 MiB | 382 MiB | 1.48× |

The two new independent ext4 pairs used opposite installation orders. On the return to the parent branch, the paired total-size ratios were 1.3204 and 1.3204. On the return to the feature branch, they were 1.4822 and 1.4820. Both feature revisions’ programs matched their separately clean ELF files. Both installations rejected a deliberately invalid Rust edit and recovered its original program.

After the return to the feature branch, the older session exclusively referenced about 60 MiB of dependency graphs, 27 MiB of cached query results, 11 MiB of codegen objects and 9 MiB of other metadata. The older session used 107 MiB in total. The net difference between compilers was 124 MiB because the newest session can also differ. The original 12-pair study measured just the two affected crates’ finalized incremental state. Its 107 → 231 MiB measurement applies to that narrower scope. [Original measurements](../README.md)

Physical blocks include directory allocation, small lock and fingerprint files, and symlinks. Independent cold runs can differ by a few filesystem blocks. This experiment measures steady storage for the parser build. Run the census on other crate graphs to measure their footprints.

```sh
python3 -IB verify.py
```
