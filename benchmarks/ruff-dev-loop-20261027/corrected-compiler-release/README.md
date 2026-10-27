# Optimized compiler correction and Ruff native consumer

The release compiler used the Linux release-14 PGO and BOLT inputs. The compiler directory is Git tree `9e52c043880793c40fedf3eb137a231479d9adba` at both implementation commit `3a9e8ee19f74` and final fixture commit `66815c41574c`. The source manifest verifies the complete set of changed compiler files against the release baseline. The release receipt records the exact parent and candidate driver, frontend, and profile digests.

The formatted run-make test passes with the stage-1 and optimized corrected compilers. At the original PR head it fails the new source-file-ordinal assertion because the producer hash stays equal across a newly inserted private sibling.

An external Cargo binary calls Ruff’s `SourceCode::line_end_exclusive` for LF, CRLF and CR. The complete reversal of Ruff commit `88d851449d` changes its output from `1 1 1` to `1 2 1`. Both optimized compilers produced the expected result in warm and independent empty-store builds, then restored `1 1 1` after the edit was undone. Each changed-source run compiled the producer and the binary. Fresh checks launched zero compilers.

The complete consumer ELFs are byte-identical across arms and cache histories within each source state. The producer metadata, API hash and diagnostics match warm and clean copies within each arm. The raw producer rlibs differ on both arms. Comparing the restored warm and clean archive members found byte-identical contents for each of the 14 codegen-unit objects and for the embedded metadata. The object member names and the linker’s `lib.rmeta-link` entry differ. The member-level audit was performed on the retained restored artifacts.

The 16 Cargo commands are a behavioral control. The dirty-workspace timing experiments have separate preregistered samples.
