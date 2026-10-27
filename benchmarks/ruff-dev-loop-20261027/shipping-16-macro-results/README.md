# Ordinary Rust callers on Ohm 1.99.0-16

Two independent procedural-macro cache histories can produce incompatible Rust artifacts in the Linux x86-64 distribution. Six of 28 ordinary callers failed with E0460. The other 22 compiled and ran. Each failed caller combined the bridge from one history with its dependency from the other.

| Fixture | Matched native results with retained / empty state | Crossed failures |
| --- | --- | ---: |
| Parse a token from a string and expose a later span | `373862..373872` / `373864..373874` | 2 of 2 |
| No-op derive followed by `Span::call_site()` | `#6` / `#9`, both at `373748..373780` | 2 of 2 |
| No-op derive followed by `Span::mixed_site()` | `#7` / `#10`, both at `373749..373781` | 2 of 2 |

The programmatic token constructor, root syntax context and Ohm-defaults-disabled controls passed in both directions. The suites retain every invoked command, diagnostic, raw metadata file, Rust bridge archive and native output. Each executable has a SHA-256 and size. The inputs were the checksum-verified official release, Rust `9a1b7cb6a3` and Cargo `4c07cbf6bd`. These are correctness reproductions. [Ohm 1.99.0-16](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-16)

Run `python3 -B verify.py` to verify both suites against the distribution manifest, all 21 Cargo builds, 14 bridge builds, 28 compiler outcomes, and the 22 executed programs.
