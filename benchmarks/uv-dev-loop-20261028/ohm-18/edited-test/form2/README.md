# Fresh historical-stack test replica on Ohm -18

This is the prospective registration for an eight-pair, whole-workspace `cargo test --no-run --locked --offline -j8` instruction-count replication. The first checkout saved 2.10% for the full historical stack. The original second-checkout attempt stopped during baseline admission and produced zero scored observations. [Original count, rejected attempt and stock ELF comparison](../)

Two unmodified baseline builds produced different raw hashes for the ordinary `uv` executable. Of its 316,713,312 bytes, exactly 33 differ. Those bytes contain the validated GNU build ID and one byte in the `.rodata` section header. This new registration requires four baseline admissions and both complete raw hashes before recording any edited command. Every edited pair still has to agree on both reconstructed full-file hashes, report the same 72 test executables, and execute one Cargo, six rustc and five Wild processes.

The archive contains the fixed source edits, assignments, original null result, exact driver identities, independent scorer and a standalone replay command. Its detached replay returned zero and recovered all eight original pair assignments. [Registered archive](ohm18-edited-test-form2-registration.zip) · [Detached verification](detached.json)
