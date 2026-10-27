# A cached derive changed the local SourceMap used by the Ruff parser's crate hash

The release-matched #233 compiler with SHA-256 `dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f` executed the actual native Ruff parser invocation captured from ordinary full Cargo. A private clone retained its original parser incremental state and a second identical clone removed just that state. Three diagnostic executions of each history reproduce the uninstrumented Cargo outputs byte for byte. The warm raw metadata SHA is `b13e40456fbc350d83d8a68dd1f0a9ef7d8cff339ec03f42991b6830e7ca8e8c` and the empty SHA is `9ef170ebfc6e0a62e047ba377512574eee99db2968453dee172aba387c5c18b1`.

| Input to the private crate hash | Warm | Empty |
| --- | ---: | ---: |
| Bytes already hashed before frozen macro-span reads | 176,753 | 176,769 |
| Frozen macro-span map entries | 67 | 67 |
| Sorted local source identifiers | 20 | 21 |

The entire 16-byte difference in the length of the earlier hash input corresponds to one extra 128-bit local StableSourceFileId. The cold set is the warm set plus the byte sequence `4175462a3d5d2dd2d422d26af13a9c63`. Equal frozen-map lengths alone establish no equality of map contents.

At the SourceMap insertion site's preceding lookup, the cold compiler supplied an input of one byte, hexadecimal `30`, to `FileName::ProcMacroSourceCode`. The empty compilation performed this lookup 168 times for the same file, all through the actual `get-size-derive2` image (SHA-256 `056eb80114e17f1b1c834813683c4efaa746d18bd1d88f4ac481fee1385c69d7`). A stable source-file identifier indexes one allocation even when the same text is parsed repeatedly. The symbolized stack enters `proc_macro::TokenStream::from_str`, reaches rustc's `ts_from_str` server, then `SourceMap::new_source_file`. Warm compilation had no lookup for this identifier. This observer covered every ID actually hashed in both local file lists. Both collectors match the exact original raw Cargo metadata for their respective histories.

The compact Linux/x86-64 observers use dynamic symbol interposition and field locations validated against this exact compiler image. They forward real rustc calls unchanged. The fixed caller-relative and object-layout offsets, captured sources, complete raw observations and disassembly are included. Use the first reproducer only on the pinned driver. The first attempt at the sorted-ID observer instrumented a library sort path that the compiler inlined for 20 entries and stopped early. It has no accepted result. Two initial data-export attempts stopped on an indirect crate-name lookup and duplicate log copy. The final export resolves the unique recorded plugin filename in the private target and authenticates its SHA.

Run `python3 -B verify.py` for offline validation. The ordinary Cargo and Rust-caller comparisons are separate in `parser-incremental-components-h3`. A standalone natural reproduction in `proc-macro-parse-baseline-h3` exercises the actual behavior, including runtime output on earlier and later compilers. These diagnostic commands are unscored.
