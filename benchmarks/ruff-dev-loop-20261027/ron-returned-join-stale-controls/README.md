# A real foreign-span join alongside an independently changing input

Ruff's locked ron 0.12.0 produced exactly three writes to the observed-foreign-bytes marker in the earlier native debugger run. The debugger watched five specific marking sites. It kept the first backtrace at each site and collected both input registers for every join. Its single saved join backtrace reached serde_derive serializing a newtype struct through syn and quote. Rust call stacks for the other two hits were not recorded in this diagnostic. At each of the three joins, one input had length 1 and the other had length 8, with identical hygiene and positions 53 bytes apart. In bitflags 2.13.2, the generated field's first and last tokens are the opening angle bracket and the identifier Internal in src/public.rs:17. They have these exact relative positions and lengths. The initial argument-register moves in the compiler and the original debugger-output commitment are included. The small independent derive reproduces that specific input and copies its joined span onto a token returned to a second macro. Its compiled program reports columns 37 through 98.

A one-byte space-to-newline edit preserved the complete length and both exact byte ranges but changed the reported location to line 18, columns 36 through 97. The source-built Ohm compiler’s emitted public hash changed for this edit. Inserting 48 bytes into an unrelated earlier caller source moved absolute Debug positions by 48 while the file-relative reader stayed stable. A cross-file join returned None. These are correctness probes on a private copy of the pinned crate. The full ron trace is separate.

## Synchronized source and native library controls

The holdout ran the exact same successful foreign join while a second ordinary macro either expanded a builtin include_str! or returned two bytes read from its loaded native library. A writer waited for the macro to acknowledge 17 and atomically replaced the selected input with 29 before rustc could emit the dependency file. Both replacements preserved size and nanosecond modification time. For the library, exactly two bytes in the read-only data section differ, with the complete .rustc section and machine code identical. Each history used a fresh private target, trained the observer, changed the caller source, made the synchronized replacement, ran two unchanged builds, and separately compiled an empty-target reference. A forced compile in the original target kept the very same replacement DSO or included file and printed 29. Every reported executable was run.

| Cargo and rustc | Join marker | Two unchanged builds after replacement | Empty and forced same input |
| --- | --- | --- | --- |
| #261 and source-built #233 | Original | 29, 29; one real app compiler each | 29 |
| #261 and source-built #233 | Omitted only at join | 17, 17; both fresh, zero compiler jobs | 29 |
| #261 and official -17 | Original | 29, 29; one real app compiler each | 29 |
| #261 and official -17 | Omitted only at join | 17, 17; both fresh, zero compiler jobs | 29 |
| Released -17 Cargo and rustc | Original | 17, 17; both fresh, zero compiler jobs | 29 |

Both independent input types gave the table's result. The two corrected-Cargo trials used its real release-profile binary at 0aa04df8. The other Cargo was the official Linux -17 executable. The experiment used a compiler-entry wrapper on isolated inputs. On the app compiler the diagnostic binds the release symbol, verifies the instruction encoding, and optionally NOPs only the seven-byte observed-bit store in that process. It keeps expansion-cache invalidation and the real Span::to call. The unchanged-driver controls use the identical preloader without changing any instruction. The raw Rust depfile confirms precisely whether the marker was present, and the compiled application returns the actual joined location in every phase. There is no elapsed-time result. The independently built cold DSO uses the 29 source value; the extra forced-build control retains exactly the live replacement bytes.

A different tiny real proc macro tracked the original library path and an existing hardlink. It compared its own static's actual /proc/self/maps inode with the named alias. The original and a copy bind-mounted over exactly the same logical DSO pathname both had identical file bytes and link count two. The compiler-produced program changed from alias=true to alias=false, even though the mapped name remained identical. Binding both named paths to the same copy restored the alias relationship. This establishes a limitation of a byte-copy sandbox. There is no claim that serde derives inspect these paths.

## Reproduction

Run `python3 -IB verify.py` to check the exported native products, compiler calls, two backdated inode changes, raw source/diagnostic/per-command hash commitments, both clean and forced same-input references, and the source-layout and live-mapping controls. SHA256SUMS authenticates the packet. The opaque raw logs stay in their private native fixtures.

On x86-64 Linux with the tested release toolchain, supply a private matching SDK, the exact Cargo and rustc driver, an unmodified unpacked bitflags 2.13.2, and a directory containing the rustup proxy. Each work directory must be new. The active-worktree credentials and registry configuration are unnecessary. Run from this directory.

```sh
mkdir -p runtime
cc -shared -fPIC -O2 -Wall -Werror join-diagnostic.c -ldl -o runtime/libjoin-diagnostic.so
python3 -B sync.py --sdk "$sdk" --cargo "$cargo_image" --driver "$driver" \
    --bitflags "$bitflags" --rustup-bin "$rustup_proxy_dir" --work "$work"
python3 -B force-current.py "$work" "$sdk"
python3 -B extract.py "$work" > reproduced.json
```

For the unmodified official pair pass `--variants keep`. For the semantic/location-only tests, set OHM_HOLDOUT_SYSROOT to the matching SDK, use the corresponding private rustup +ohm alias and use `RUSTC_BOOTSTRAP=probe python3 -B run.py --bitflags "$bitflags" --work "$new_work"`. The topology test additionally requires unprivileged bubblewrap and `python3 -B maps-control.py "$new_work"`. The portable fixed release test intentionally recognizes the Linux x86-64 instruction form and fails if it cannot verify the site.

The tiny combined witness is distinct from the [trained official -17 file witnesses](https://github.com/astral-sh/ohm-cargo/tree/55fc99a09e3bb529294de08dd73f372abae22dd3/benchmarks/ruff-dev-loop-20261027/noquery-established-observer-results), [metadata and DSO witnesses](https://github.com/astral-sh/ohm-cargo/tree/d94e602e0f3b0eb357e9a386e3fc27971727937b/benchmarks/ruff-dev-loop-20261027/synchronized-compiler-inputs), and [actual 45 ron prerequisites](https://github.com/astral-sh/ohm-cargo/tree/dedb84c81411412d96ba719d4ee49a0e0563aeae/benchmarks/ruff-dev-loop-20261027/ron-native-input-origins).
