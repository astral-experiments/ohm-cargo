# Official `ty_wasm` builds in a target directory with a space

This unscored Linux check used the actual public Ohm 1.99.0-16 and 1.99.0-17 x86-64 packages. Two separate full installations answered through a private `+ohm` selector. Each build ran from the clean `crates/ty_wasm` directory at Ruff commit `93526150df078af7dd8fc4226cdcc469539d2001`. The SDK, Cargo home and Rust sources were unspaced. Both releases saw the same canonical spaced target name `ruff target`, backed by their own initially empty target, shared build and hydrated registry. [Ohm 1.99.0-16](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-16) · [Ohm 1.99.0-17](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-17).

Each of the eight commands was `cargo +ohm build --locked --offline -j4 --message-format=json`. Native traces identify the actual packaged compiler and linker by executable identity. The separately invoked caller and all output checks ran after Cargo.

| Release and state | Fresh units / 304 | Full compiler jobs | Link-only compiler jobs | Wild links | Other linkers |
| --- | ---: | ---: | ---: | ---: | ---: |
| -16 Cold | 0 | 305 | 0 | 50 | 0 |
| -16 Unchanged 1 | 298 | 2 | 0 | 1 | 0 |
| -16 Unchanged 2 | 298 | 2 | 0 | 1 | 0 |
| -16 Unchanged 3 | 298 | 2 | 0 | 1 | 0 |
| -17 Cold | 0 | 305 | 0 | 50 | 0 |
| -17 Unchanged 1 | 304 | 0 | 0 | 0 | 0 |
| -17 Unchanged 2 | 304 | 0 | 0 | 0 | 0 |
| -17 Unchanged 3 | 304 | 0 | 0 | 0 | 0 |

All three unchanged -16 builds reran the same two Rust crates and Wild. All three unchanged -17 builds reported 304 fresh units, and no actual compiler, compiler query or linker ran. The typed traces retain every native process, 304 Cargo rows, and input/output commitments for every invocation. Conditions and outputs are specific to this workspace member and target path.

Every completed build supplied its own `ty_wasm` and `ty_vendored` libraries to an independently compiled Rust caller. The 210 library search directories were taken from its genuine rustc process. The native caller required `ty_wasm::version() == "93526150d"` and returned all 18,553 source bytes of `stdlib/functools.pyi`, SHA-256 `721696b22e172c4f9dbe15ec5e04a04a9939188eca12d8110ab62f9de81d96a1`. The complete compressed 1,478,740-byte ZIP occurred contiguously in both the `ty_vendored` rlib and its rmeta, at recorded offsets. Separate final native cdylib, compressed ZIP and complete source bytes for both packages remain on the validation host.

The final Linux cdylib SHA-256 was `50878e5f1f815ec78e6aaa85dfebd55c6e84df143386c3bc12dccc690c580d87` for -16 and `58c67a7470edadb578948ba33eb89f29bccf1e19de498b62ef342cb91f7b78c6` for -17. The release archives, actual frontends, drivers, Cargo and Wild signatures are recorded separately in the packed subject data.

Run `python3 -IB verify.py` to replay the process, workspace and native witness checks offline. The package worker, independent source reader, typed inputs and trace commitments are in `observations.tar.gz`.
