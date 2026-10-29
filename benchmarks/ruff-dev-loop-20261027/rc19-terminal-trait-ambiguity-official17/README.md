# Official Ohm 1.99.0-17 also accepts the ambiguous terminal check

The published Linux -17 SDK reproduced the same missed `E0034` in the untouched four-crate client as -18. The installed Cargo is a0c7d08c8. Both provider-late edits returned zero, compiling only the provider and the reexporting reader. Both immediate checks then declared all four crates fresh, launched no rustc, and also returned zero. An empty check of each edited source genuinely compiled `client` and reported the ambiguity at its `Token.priority()` call. The two provider-first edits and their repeats correctly failed in the same leaf. All four recoveries succeeded and their next checks were entirely fresh.

The host downloaded the authenticated GitHub release asset with ID 683546983. It matched the independently retained 359,683,716-byte archive and SHA-256 `163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572`. The native compiler, driver, Cargo, and bundled linker matched all four recorded artifact digests after a fresh installation. The 22 ordinary check commands use separate private build and target directories, the same forwarded timestamp-call interposer as the primary packet, and four independent branches of the original warm state. This establishes the released behavior in -17 and -18. [Ohm -17 release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-17)

`official-17.json` contains each diagnostic, physical Rust invocation, committed fingerprint, hook transcript, source identity, and SHA-256 of each original trace and output file. The projection reassembles any split successful `execve` before counting a compiler. The actual Rust artifacts show the provider's public hash changed and the reader's remained equal. Cargo marked the reader unchanged while waiting for the provider's final metadata disposition.

Place the primary four-crate packet on disk and pass its directory to the verifier. Its required manifest SHA-256 is `53e1b6d317a749982edd6ff1cbb9362e865734a67cfcfa094c02c804654070ea`.

```sh
python3 -IB verify.py --core /path/to/four-crate-primary-packet
python3 -IB /path/to/four-crate-primary-packet/reproduce.py /path/to/ohm-17 /tmp/unique-17-late provider-late --expect stale
python3 -IB /path/to/four-crate-primary-packet/reproduce.py /path/to/ohm-17 /tmp/unique-17-first provider-first --expect correct
```
