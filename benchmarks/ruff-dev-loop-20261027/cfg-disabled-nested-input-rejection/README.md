# A nested native input invalidates a previously trained empty-test ELF

The three frozen Cargo binaries used the same #233 Rust compiler and Wild linker. A ran shipping Cargo #254. B included the candidate’s one-worker training support and always performed a full compile and link. C could skip the certified cfg-disabled integration test after training. A separate, unused registry-free Rust dependency changed on every invocation.

Inside private mount namespaces, the selected system libutil.a was an unchanged linker script containing `INPUT ( x86_64-linux-gnu/librt.a )`. Its initial fallback was the genuine system librt.a, an eight-byte empty archive. The candidate’s certificate covered the fallback bytes and the SDK directory, but missed the nested pathname relative to that directory.

| Higher-priority SDK pathname | Shipping Cargo and fixed-width full control | Candidate after training |
| --- | --- | --- |
| Absent | Successful test binary with no marker symbol | Same |
| Contains a valid native object | Successful binary contains symbol ohm_nested_input_marker at 0x97 | Reused old binary without the symbol |
| Contains a script naming a nonexistent object | Wild failed, Cargo exited 101 | Reused old binary and exited 0 |
| Removed again | Successful binary with the original hash | Same previously retained binary |

This reproduced with real rustc, GCC, collect2, Wild, ELF and `nm` observations. All original system files stayed untouched. A relinked all four times. B did too. C performed only the upstream Rust compile, and its unchanged one-worker certificate and prior ELF passed all four checks. The native timing plan for this candidate was stopped before collecting a scored command. The failure concerns the experimental Cargo shortcut. [Source and phase registration](https://github.com/astral-sh/ohm-cargo/tree/570f3907a2de224dd6095e11988b772ec2dec318/benchmarks/ruff-dev-loop-20261027/cfg-disabled-fixed-link-width-plan)

Run `python3 -B verify.py` to check the 18 command outcomes, per-process trace hashes, symbol, failure diagnostic, and unchanged certificate. The fixture and extractor use the documented H1 native study layout.
