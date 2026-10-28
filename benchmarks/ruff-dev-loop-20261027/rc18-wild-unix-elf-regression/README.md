# Native Unix filenames in Wild 0.11.0

Ohm 1.99.0-16 and -17 bundle the same Linux Wild executable. An ordinary Cargo build of the small C-ABI caller panicked on both releases when either `TMPDIR` or `LIBRARY_PATH` contained byte FF. The Cargo command, project path and Rust flags stayed the same. The real GCC driver supplied a byte-valued `-plugin-opt=-fresolution=…` or `-L…` argument to Wild. An ASCII response filename with byte FF in its body instead made stock Wild exit 1 with an input-reading error. The bundled rust-lld linked both input forms.

The private draft preserves native bytes in supported ELF operands. The qualified implementation is commit `38eb35bd8b76dad3e97e027cc52d8e89fd3bc263`, on the exact 0.11.0 release commit `e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11`. Its source patch digest is `62debcbfd9042c9b1d79bd27b9ca101c191e15e9dfd949cfc5294f395626072f`. Two separate hosts built the same 10,315,032-byte ELF, SHA-256 `9de3bdd6675f02e08d687045383c097ab0ef6027c779f153a7823153ecf8445e`. Each build used the default feature set in the pinned public Rust image, the original release archive and the same `cargo build --locked --profile dist --package wild-linker --bin wild --target x86_64-unknown-linux-gnu` at `/work/source`. The local reproducer's Cargo and rustc versions, return codes, license digests and file modes are in `subjects.json`. [Wild draft](https://github.com/astral-sh/ohm-wild/pull/44)

## Native controls

| Workload | Released Wild | Source-built Wild |
| --- | --- | --- |
| Ordinary Cargo with raw GCC temporary directory | Wild panic | Program prints 41 |
| Ordinary Cargo with raw GCC library directory | Wild panic | Program prints 41 |
| Library directory spelled with U+FFFD | Program prints 99 | Program prints 99 |
| Ordinary Cargo with a raw object inside GCC’s UTF-8-named response | Wild exits 1 | Program prints 41 |
| Raw input, raw output or response filename | Wild panic | Fixed-width native ELF matches the ASCII operand control |
| Raw no-SONAME DSO | Wild panic | The loader requires the exact FF-containing path and exits 127 when it disappears |
| UTF-8 nested response, quoted spaces, Unicode whitespace and push/pop of as-needed | Program returns 41 | Same raw ELF and both original DT_NEEDED entries |

The final package also preserves native names in ELF base version definitions, sysroot search, Make prerequisites and the input trace. A first private version wrote the replacement spelling into the base version and depfile and selected an actual library returning **99** instead of **41** under `-L=/lib<FF>`. Those engineering results remain in `observations.json`. The UTF-8 parity fixture initially tested a reused save directory that the stock linker had cleared. The repeated native control gave each arm its own seeded directory. Stock cleared its sentinel before panicking and the corrected linker emitted a clean diagnostic while preserving its sentinel.

This implementation covers input files, the executable output, library search directories, plugin arguments and response-file names and contents. Text-valued options such as `-rpath`, raw `--version-script`/library-name arguments, saved-link replay and non-ELF CLI parsing can reject non-UTF-8 values. A non-UTF-8 Cargo workspace root or rustc output directory failed earlier in those tools on both product arms. No Cargo scheduling or wall-time result is claimed for this repair.

## Reproduction

`python3 -B verify.py` rechecks the package and observed native comparisons without a toolchain. To rerun the real commands use Linux x86-64, GNU as/ar/GCC, strace, rustup and clean caller-owned space. Supply extracted SDKs. For the candidate, bind or copy **only** the verified candidate binary over `lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd` in a private SDK and retain the stock rust-lld executable.

```sh
python3 -B qualify.py /tmp/new-wild-path-cli old=/path/to/stock-sdk new=/path/to/private-sdk
python3 -B cargo_env.py /tmp/new-wild-path-env old=/path/to/stock-sdk new=/path/to/private-sdk
mkdir -p /tmp/new-wild-path-oracles
python3 -B elf.py /tmp/new-wild-path-oracles elf /path/to/candidate-wild /path/to/stock-sdk
python3 -B sidecars.py /tmp/new-wild-path-oracles sidecars /path/to/candidate-wild /path/to/stock-sdk
python3 -B utf8.py /tmp/new-wild-path-oracles compatibility /path/to/candidate-wild /path/to/stock-sdk
```

The two fresh Cargo fixtures use only the SDK alias inside their own private rustup homes. The direct probes run actual ELF programs including a different valid U+FFFD decoy. `source-receipts.json` seals the private command records used for this export. It does not give access to the files themselves.
