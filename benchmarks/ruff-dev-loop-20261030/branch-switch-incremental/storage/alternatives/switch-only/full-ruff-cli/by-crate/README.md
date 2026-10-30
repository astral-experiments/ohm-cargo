# Final whole-CLI object and metadata growth by Rust crate

This read-only diagnostic reopens both final B inode lists from the twelve-command 08d49 packet with SHA-256 manifest `f0299ce8b1d2cf598f35aef59f460e99b428e2a01873e2ca9623a293d24e52f0`. It adds no builds. For incremental names it extracts the literal rustc crate name found after the Cargo workspace key in the incremental directory. Multiple targets with the same Rust crate name are grouped. Potentially mixed or unrecognized names remain explicit. Each inode is counted once across all of its paths. The diagnostic checks that its class sums agree with the original full namespace census.

Of the additional 174.20 MiB of native objects, 90.09 MiB was in `ruff_linter`'s incremental directories. The next largest changes were `ruff_workspace` at 12.97 MiB, `ruff` at 12.64 MiB, `ruff_server` at 12.14 MiB and `ruff_db` at 11.85 MiB. The extra 36.23 MiB of Rust metadata included 14.59 MiB in `ruff_linter` and 6.11 MiB in `ruff_python_ast`. The entire 4.66 MiB increase in the main packet's other regular files comprised 4,800,512 bytes of metadata prefixes and 81,920 bytes of metadata.bin. The measurements give physically distinct allocated bytes. They do not compare the contents of different inodes for deduplication.

```sh
sha256sum -c SHA256SUMS
python3 -IB by-unit.py /path/to/main/storage-packet | diff - by-unit.json
```
