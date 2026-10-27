# A cached no-op derive changes observable hygiene on shipping Ohm

On the published Linux x86_64 Ohm 1.99.0-15 toolchain, a derive returning an empty token stream changes what a subsequent procedural macro prints after an unrelated Rust edit. The two local crates have no registry dependencies. Neither Rust macro parses a token string. The first returns `TokenStream::new()`. The second formats a span into a Rust string literal. An independently compiled native executable prints that literal.

| Later macro reads | Retain the producer’s incremental state | Empty only that state | Ordinary crossed callers |
| --- | --- | --- | --- |
| `Span::call_site()` | `8:#6 bytes(373748..373780)` | `8:#9 bytes(373748..373780)` | Both fail with E0460 |
| `Span::mixed_site()` | `8:#7 bytes(373749..373781)` | `8:#10 bytes(373749..373781)` | Both fail with E0460 |
| Input token’s root span | `8:#0 bytes(373776..373786)` | `8:#0 bytes(373776..373786)` | Both pass |
| `Span::call_site()` with Ohm defaults disabled | `8:#9 bytes(373748..373780)` | `8:#9 bytes(373748..373780)` | Both pass |

The byte offsets agree in every row. The exposed hygiene context identifier and the producer’s private crate identity differ in the first two rows. For each of those rows, a bridge compiled against either producer successfully links and runs with the same producer. Loading that bridge with the other producer fails during a fresh, conventional rustc invocation.

Every case trained at the same logical source and target paths as its warm and empty builds. The library changes a real return value from 7 to 8. The compiled macro image stays byte-identical between histories, and neither local trust override is set. Both the Cargo executable and compiler driver matched the official archive components. This correctness probe ran no timed endpoint. [Published distribution](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-15) · [Installation and archive verification](https://github.com/astral-sh/ohm-cargo/tree/67e2a6e170d2717320e973c4ee69792692c282fa/benchmarks/ruff-dev-loop-20261027/shipped-15-proc-macro-span)

Run `python3 -B verify.py` and `sha256sum -c SHA256SUMS` for offline verification. The packet contains all twelve Cargo builds, eight separately compiled bridges, sixteen new caller compilations and twelve executed programs’ output. The checksums bind every executable and bridge archive observed on the release host. The stand-alone `hygiene-sites.py` reruns all four cases against a private Linux rustup descriptor with the supplied Cargo and compiler driver.
