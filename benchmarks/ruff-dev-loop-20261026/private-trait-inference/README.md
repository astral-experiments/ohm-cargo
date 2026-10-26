# Private trait impls observed through downstream inference

This independent review exercised the stage-2 compiler from Ohm Rust `2fab350c4786367432b5e1d767ed8e1ced431f41`. Each fixture has a foreign trait crate, an intermediate library with the private type, and an unchanged downstream user. The 23 cases cover observable associated types and constants, layout and auto traits, enum discriminants, nested bounds, inference through a second trait and overlapping impls. [Exact source for all three crates](cases.json)

Sixteen edits changed a downstream program from valid to invalid. The intermediate crate's public hash changed in all sixteen. A change to an isolated private payload kept its hash. Bare unknown-self inference remained ambiguous before and after. A dependent coherence overlap kept its expected error. [Direct compiler results](direct-results.json)

All 23 cases were also run with real Ohm Cargo. The first two commands used the same warm target before and after the edit. The third compiled the edited workspace from empty target and build directories. In all 23 cases, warm and clean produced identical public hashes and error diagnostics, including rendered text. The driver SHA-256 was `051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518`. The later PR head renamed the existing test fixture so CI discovers it. [69 complete check results](cargo-results.json), [Ruff invalidation, language and ELF evidence](../private-trait-check/)

Configure the `+ohm` alias with that compiler and run the following command with a new state directory. The script creates the sources and uses ordinary `cargo +ohm check`. It reads the producer's public hash from the metadata emitted by Cargo.

```sh
python3 replay.py "$NEW_PRIVATE_STATE" "$RESULTS_JSON"
```
