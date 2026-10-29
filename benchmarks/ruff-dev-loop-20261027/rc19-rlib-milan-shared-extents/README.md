# Physical extent reuse in the earlier Milan Ruff archive witness

The new writer's genuine edited Ruff archive retained 100,994,828 of the original 101,719,820 bytes at the same Btrfs physical addresses and logical offsets (99.29%). Both files' extent reports marked all of those shared. The ordinary writer's edited file shared zero physical bytes with the original at corresponding offsets. Both compiler outputs had already matched an independently reconstructed archive from their own 258 actual input files. [Registered current-input witness](https://github.com/astral-sh/ohm-cargo/tree/a644772c28607282fc06bb7c72f08225ea04f0a6/benchmarks/ruff-dev-loop-20261027/rc19-rlib-current-input-witness-plan)

| Comparison | Equal physical bytes at the same logical offset | Bytes in equal 64 KiB data comparisons |
|---|---:|---:|
| Original to edited ordinary writer | 0 | 100,933,388 |
| Original to edited clone writer | 100,994,828 | 100,933,388 |
| Edited ordinary to edited clone writer | 0 | 101,523,212 |

The read-only observation used three previously sealed subvolumes in one single-data-profile Btrfs image. The original files were opened with O_NOATIME on a read-only block device, with log replay disabled. FS_IOC_FIEMAP used flags zero. File identity and content hashes, then the whole extent tables, were rechecked. None reported opaque, encoded, delayed, unwritten or unmapped bytes. A 64 KiB block containing even one differing byte counts as unequal in the right column. Extent boundaries and data-comparison boundaries are independent.

The export subtracts one common origin from every physical address. The included verifier reads every extent, intersects the tables, checks the kernel flags, recomputes coverage and retains the independent full-file hashes and comparison interval totals. Run `sha256sum -c SHA256SUMS && python3 -IB verify.py`. The original physical console receipt and acquisition program are identified by SHA-256 in `extents.json`. The result measures retained allocation on this image. It contains no command-time observation.
