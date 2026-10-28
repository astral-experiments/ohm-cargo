# A native selector distinguishes byte-identical Ruff codegen objects

Using the actual released Ohm 1.99.0-16 Wild and actual Ruff Unicode runtime archives from the generated-lifetime edit, a small native program returns 42 with the original archive and 41 with both the edited and restored-source archives. The complete ordered set of 13 native object payloads, the 37 symbol-to-member ordinals, the selected machine code, the observer source and the linker script all agree. The generated native object has a different archive member name in each physical build.

The unchanged GNU linker script selects the Rust section containing the real `unicode_names2::name` function by its original archive member name. The function at GNU archive ordinal 12 contains 484 bytes. Wild’s selected output section spans 496 bytes after its 16-byte alignment padding on the original. The same named section contains zero selected bytes on the edited and restored-source archives. The Linux x86-64 assembly reads the two linker-defined outer addresses and makes its exit status depend on their difference. It does not execute the Rust function. The raw full-link commands use `-static`, section GC, an explicit reference to the Rust symbol and a policy allowing unresolved unused Rust code. This is an adversarial user-supplied linker script. The ordinary Ruff CLI in the separate generated-source experiment has its normal linker arguments and an identical final ELF through all three source conditions.

| Full library | Hit on original physical member name | Selected output-section bytes | Native exit |
| --- | --- | ---: | ---: |
| Original | yes | 496 | 42 |
| Reverted generator templates | no | 0 | 41 |
| Original source restored | no | 0 | 41 |

A second host reproduced all three statuses and symbol distances with the exact same full input rlibs and Wild SHA. Its 242,528-byte native program differed from the first host in exactly one byte for each comparison, the `.rodata` section header's `sh_entsize`. The literal offsets and both whole-ELF digests are in `independent/whole-elf-deltas.json`.

A portable minimized replay uses the real, unchanged 114,296-byte Rust codegen object, independently repackaged under each of the three actual member names. The self-contained replay reproduced the same 42, 41, 41 exits and 496, 0, 0 address differences. Its three raw ELFs are included. The three executable files linked from the full native archives include private registry paths and are retained privately. `receipts.json` gives original byte lengths and digests for every one of the 68 H3 records. The actual native commands, unchanged script, returned status, readelf symbol table, section headers and stderr are available.

The first diagnostic expected the selected output-section distance to equal the 484-byte raw input function length. The initial link succeeded, and its assertion recorded 496. A separate readelf check identified 16-byte output alignment and a 484-byte function, followed by a separately labeled three-phase run with the explicit output bound. Both attempts are preserved.

Run `python3 -B verify.py` and `sha256sum -c SHA256SUMS` to check the archived records. To independently run the portable native filter on Linux x86-64 with GCC, GNU ar, nm, readelf and the specified Wild, use `python3 -B replay.py --wild /absolute/path/to/ld.bfd --workdir /temporary/new-dir`. The Wild SHA-256 is `0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5`. Add `--archive-dir` pointing to a directory containing the full native rlibs under their SHA-256 filenames for the full-library replay.
