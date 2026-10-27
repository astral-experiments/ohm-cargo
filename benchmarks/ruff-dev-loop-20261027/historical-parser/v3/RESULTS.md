# Historical formatter compilation

The compiler skip reproduced on every complete replay of Ruff’s 2024 missing-exception change. The elapsed-time study was excluded by its predeclared symbol-witness requirement.

| Endpoint | Commands per arm | Cargo units | Parent full / relink | Candidate full / relink |
| --- | ---: | ---: | ---: | ---: |
| `cargo build -p ruff_python_formatter` | 32 | 94 | 3 / 0 | 1 / 1 |
| `cargo test -p ruff_python_formatter --no-run` | 32 | 107 | 7 / 0 | 1 / 4 |

Each command had its own fully fresh prerequisite. All materialized machine code, data, dynamic exports, relocations, unwind tables and debug information had the expected byte hashes on every replay. Every runtime sample, compiler diagnostic and producer hash guard also passed. The public hash stayed stable for each candidate edit while the parser’s changed code was compiled and its new error reached the consumer.

The remaining guard admitted a static symbol only with an exact observed name from the old compiler, including LLVM’s numeric private-label suffix. One build treatment observation used a complete combination absent from 30 preflight runs, the 32 randomized old-compiler observations and 64 subsequent independent old-compiler builds. Its symbol names differed only in the previously enumerated hidden numeric labels. Each symbol’s binding, type, visibility, address, size, section and full name prefix agreed. The build gate stopped the protocol before the test witness phase. The complete elapsed measurements are retained without a timing estimate or significance claim.

`rows.jsonl` contains all 256 randomized or prerequisite rows. `post-witnesses.jsonl` contains the 64 extra old-compiler observations. `command-receipts.json.gz` contains all 384 corresponding command receipts with their actions, outputs and section hashes. `command-arguments.json.gz` stores the deduplicated argv and Cargo unit graphs. Run `python3 verify-observations.py` to check the qualification and retained symbol differences.
